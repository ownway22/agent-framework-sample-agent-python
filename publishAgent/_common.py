from __future__ import annotations

"""
publishAgent 共用工具。

步驟 1: 提供路徑、輸出與命令執行等基礎工具。
步驟 2: 集中處理環境變數、JSON 與簡單驗證。
步驟 3: 讓各腳本可以專心描述流程，不必重複寫樣板程式。
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


# 步驟 1: 統一路徑來源，避免各腳本自己拼接目錄。
def script_dir() -> Path:
    return Path(__file__).resolve().parent


def repo_root() -> Path:
    return script_dir().parent


def env_file_path() -> Path:
    return repo_root() / ".env"


def config_path() -> Path:
    return repo_root() / "a365.config.json"


def generated_config_path() -> Path:
    return repo_root() / "a365.generated.config.json"


def manifest_dir() -> Path:
    return repo_root() / "manifest"


# 步驟 2: 提供一致的終端輸出格式，讓初學者容易追流程。
def print_header(title: str) -> None:
    line = "=" * 80
    print(line)
    print(title)
    print(line)


def print_step(message: str) -> None:
    print(f"[publishAgent] {message}")


def fail(message: str, exit_code: int = 1) -> int:
    print(f"[publishAgent] ERROR: {message}", file=sys.stderr)
    return exit_code


# 步驟 3: 封裝命令檢查與執行，減少重複樣板。
def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def require_command(command: str, install_hint: str | None = None) -> None:
    if command_exists(command):
        return
    hint = f" Install it first: {install_hint}" if install_hint else ""
    raise RuntimeError(f"Required command '{command}' was not found.{hint}")


def run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture_output: bool = False,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    return subprocess.run(
        args,
        cwd=cwd,
        env=merged_env,
        text=True,
        capture_output=capture_output,
        check=check,
    )


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# 步驟 4: 將常用資料處理集中管理。
def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return normalized or "agent"


def is_guid(value: str) -> bool:
    return bool(GUID_RE.match(value))


def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def wait_for_http(url: str, timeout_seconds: int = 60) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if 200 <= response.status < 500:
                    return True
        except (URLError, OSError):
            time.sleep(1)
    return False


# 步驟 5: 先讀環境變數，再視需要進入互動式輸入。
def prompt_value(
    env_keys: list[str],
    prompt_text: str,
    *,
    default: str | None = None,
    required: bool = False,
    validator: callable | None = None,
) -> str:
    for key in env_keys:
        value = os.getenv(key)
        if value:
            if validator and not validator(value):
                raise ValueError(f"Environment variable {key} has an invalid value: {value}")
            return value

    if not sys.stdin.isatty():
        if required and default is None:
            raise RuntimeError(
                f"Missing required value for '{prompt_text}'. Set one of: {', '.join(env_keys)}"
            )
        if default is not None:
            return default
        return ""

    while True:
        suffix = f" [{default}]" if default else ""
        raw = input(f"{prompt_text}{suffix}: ").strip()
        value = raw or default or ""

        if not value and required:
            print("This value is required.")
            continue
        if validator and value and not validator(value):
            print("The value format is invalid. Please try again.")
            continue
        return value


# 步驟 6: 載入 .env 供所有 publishAgent 腳本共用。
def load_env_file(path: Path | None = None) -> None:
    target = path or env_file_path()
    if not target.exists():
        return

    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value


def bool_from_env(env_keys: list[str], default: bool) -> bool:
    for key in env_keys:
        value = os.getenv(key)
        if value is None:
            continue
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
        raise ValueError(f"Environment variable {key} must be a boolean value, got: {value}")
    return default


# 步驟 7: 快速確認 CLI 登入狀態，避免執行到一半才失敗。
def detect_az_login() -> bool:
    if not command_exists("az"):
        return False
    result = run_command(["az", "account", "show"], capture_output=True)
    return result.returncode == 0


def detect_a365_login() -> bool:
    if not command_exists("a365"):
        return False
    result = run_command(["a365", "config", "display"], cwd=repo_root(), capture_output=True)
    return result.returncode == 0


def read_config_value(key: str, default: Any = None) -> Any:
    return load_json(config_path()).get(key, default)
