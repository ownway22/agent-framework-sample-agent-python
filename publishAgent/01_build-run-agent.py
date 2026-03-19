from __future__ import annotations

"""
步驟 1: 啟動本機 Agent Host。
步驟 2: 視需要啟動 Microsoft 365 Agents Playground。
步驟 3: 持續監看兩個程序，直到使用者手動停止。
"""

import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from _common import (
    fail,
    is_port_open,
    print_header,
    print_step,
    repo_root,
    require_command,
    wait_for_http,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the sample agent and Microsoft 365 Agents Playground locally."
    )
    parser.add_argument(
        "--agent-port",
        type=int,
        default=3978,
        help="Port used by the local agent host.",
    )
    parser.add_argument(
        "--playground-port",
        type=int,
        default=56150,
        help="Port exposed by Microsoft 365 Agents Playground.",
    )
    parser.add_argument(
        "--skip-playground",
        action="store_true",
        help="Start only the agent host and skip Agents Playground.",
    )
    return parser.parse_args()


def socket_inodes_for_port(port: int) -> set[str]:
    target_port = f"{port:04X}"
    inodes: set[str] = set()

    for proc_net in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(proc_net, encoding="utf-8") as handle:
                next(handle, None)
                for line in handle:
                    parts = line.split()
                    if len(parts) < 10:
                        continue

                    local_address = parts[1]
                    state = parts[3]
                    inode = parts[9]
                    _, local_port = local_address.split(":")

                    if local_port == target_port and state == "0A":
                        inodes.add(inode)
        except FileNotFoundError:
            continue

    return inodes


def pids_listening_on_port(port: int) -> set[int]:
    inodes = socket_inodes_for_port(port)
    if not inodes:
        return set()

    pids: set[int] = set()
    current_pid = os.getpid()

    for proc_dir in Path("/proc").iterdir():
        if not proc_dir.name.isdigit():
            continue

        pid = int(proc_dir.name)
        if pid == current_pid:
            continue

        fd_dir = proc_dir / "fd"
        try:
            for fd in fd_dir.iterdir():
                try:
                    target = os.readlink(fd)
                except OSError:
                    continue

                if target.startswith("socket:[") and target[8:-1] in inodes:
                    pids.add(pid)
                    break
        except OSError:
            continue

    return pids


def release_port(port: int, *, timeout_seconds: int = 10) -> None:
    if not is_port_open(port):
        return

    print_step(f"Releasing stale process on port {port}.")

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not is_port_open(port):
            return

        for pid in pids_listening_on_port(port):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue

        time.sleep(0.5)

    for pid in pids_listening_on_port(port):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            continue

    final_deadline = time.time() + 5
    while time.time() < final_deadline:
        if not is_port_open(port):
            return
        time.sleep(0.2)


def terminate_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return

    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except ProcessLookupError:
        return

    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:
            return
        process.wait(timeout=5)


def start_playground(
    *,
    root: str,
    endpoint: str,
    playground_port: int,
    playground_binary: str,
) -> subprocess.Popen[str]:
    direct_command = [
        playground_binary,
        "-e",
        endpoint,
        "-c",
        "emulator",
        "-p",
        str(playground_port),
    ]

    try:
        return subprocess.Popen(
            direct_command,
            cwd=root,
            env=os.environ.copy(),
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        if exc.errno != 8:
            raise

        print_step(
            "Local playground binary is not compatible with this machine; falling back to npx @microsoft/m365agentsplayground."
        )
        return subprocess.Popen(
            [
                "npx",
                "@microsoft/m365agentsplayground",
                "-e",
                endpoint,
                "-c",
                "emulator",
                "-p",
                str(playground_port),
            ],
            cwd=root,
            env=os.environ.copy(),
            text=True,
            start_new_session=True,
        )


def main() -> int:
    args = parse_args()
    root = repo_root()
    playground_binary = root / "agentsplayground"
    host_process: subprocess.Popen[str] | None = None
    playground_process: subprocess.Popen[str] | None = None

    print_header("Step 1 - Build and run agent locally")

    try:
        require_command("uv", "https://docs.astral.sh/uv/getting-started/installation/")
        if not playground_binary.exists():
            return fail(f"Agents Playground binary not found: {playground_binary}")
        if not os.access(playground_binary, os.X_OK):
            return fail(f"Agents Playground binary is not executable: {playground_binary}")

        release_port(args.agent_port)
        if is_port_open(args.agent_port):
            return fail(
                f"Port {args.agent_port} is still in use after cleanup. Free it before starting the local agent."
            )

        if not args.skip_playground and is_port_open(args.playground_port):
            return fail(
                f"Port {args.playground_port} is already in use. Free it before starting Agents Playground."
            )

        env = os.environ.copy()
        env["PORT"] = str(args.agent_port)

        print_step(f"Starting the local Agent 365 host on port {args.agent_port}.")
        host_process = subprocess.Popen(
            ["uv", "run", "python", "start_with_generic_host.py"],
            cwd=root,
            env=env,
            text=True,
            start_new_session=True,
        )

        agent_health_url = f"http://localhost:{args.agent_port}/api/health"
        if not wait_for_http(agent_health_url, timeout_seconds=90):
            terminate_process(host_process)
            release_port(args.agent_port)
            return fail(
                f"Agent host did not become healthy at {agent_health_url}. Check .env and model credentials."
            )

        print_step(f"Agent host is healthy: {agent_health_url}")

        if not args.skip_playground:
            endpoint = f"http://localhost:{args.agent_port}/api/messages"
            print_step(
                f"Starting Microsoft 365 Agents Playground on port {args.playground_port}."
            )
            playground_process = start_playground(
                root=str(root),
                endpoint=endpoint,
                playground_port=args.playground_port,
                playground_binary=str(playground_binary),
            )

            playground_url = f"http://localhost:{args.playground_port}"
            if not wait_for_http(playground_url, timeout_seconds=60):
                terminate_process(playground_process)
                terminate_process(host_process)
                release_port(args.agent_port)
                return fail(
                    f"Agents Playground did not become reachable at {playground_url}."
                )

            print_step(f"Agents Playground is ready: {playground_url}")

        print()
        print("Local endpoints are ready:")
        print(f"- Agent endpoint: http://localhost:{args.agent_port}/api/messages")
        if not args.skip_playground:
            print(f"- Playground UI: http://localhost:{args.playground_port}")
        print("Press Ctrl+C to stop both processes.")

        while True:
            if host_process.poll() is not None:
                return fail("The local agent host exited unexpectedly.")
            if playground_process and playground_process.poll() is not None:
                return fail("Agents Playground exited unexpectedly.")
            time.sleep(1)
    except KeyboardInterrupt:
        print_step("Stopping local processes.")
        return 0
    finally:
        terminate_process(playground_process)
        terminate_process(host_process)
        release_port(args.agent_port)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    raise SystemExit(main())