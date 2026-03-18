from __future__ import annotations

"""
步驟 1: 啟動本機 Agent Host。
步驟 2: 視需要啟動 Microsoft 365 Agents Playground。
步驟 3: 持續監看兩個程序，直到使用者手動停止。
"""

import argparse
import os
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


# 步驟 1: 先整理命令列參數，讓後續流程清楚可控。
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


# 步驟 2: 統一關閉程序邏輯，避免遺留背景程序。
def terminate_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


    # 步驟 3: 優先使用本機 Playground binary，不相容時再退回 npx。
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
        # 步驟 4: 先檢查必要工具與埠號，避免啟動後才發現衝突。
        require_command("uv", "https://docs.astral.sh/uv/getting-started/installation/")
        if not playground_binary.exists():
            return fail(f"Agents Playground binary not found: {playground_binary}")
        if not os.access(playground_binary, os.X_OK):
            return fail(f"Agents Playground binary is not executable: {playground_binary}")

        if is_port_open(args.agent_port):
            return fail(
                f"Port {args.agent_port} is already in use. Free it before starting the local agent."
            )
        if not args.skip_playground and is_port_open(args.playground_port):
            return fail(
                f"Port {args.playground_port} is already in use. Free it before starting Agents Playground."
            )

        env = os.environ.copy()
        env["PORT"] = str(args.agent_port)

        # 步驟 5: 啟動本機 Agent Host，並等待健康檢查成功。
        print_step("Starting the local Agent 365 host on port 3978.")
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
            return fail(
                f"Agent host did not become healthy at {agent_health_url}. Check .env and model credentials."
            )

        print_step(f"Agent host is healthy: {agent_health_url}")

        if not args.skip_playground:
            # 步驟 6: Host 正常後再啟動 Playground，避免 UI 先連到壞掉端點。
            endpoint = f"http://localhost:{args.agent_port}/api/messages"
            print_step("Starting Microsoft 365 Agents Playground on port 56150.")
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

        # 步驟 7: 持續監看程序，只要任一程序異常結束就立刻回報。
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
        # 步驟 8: 不論成功或失敗，都確保背景程序被清乾淨。
        terminate_process(playground_process)
        terminate_process(host_process)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    raise SystemExit(main())