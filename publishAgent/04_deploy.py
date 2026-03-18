from __future__ import annotations

"""
步驟 1: 讀取部署設定。
步驟 2: 用模擬訊息說明原本會發生的雲端部署步驟。
步驟 3: 讓教學流程可以完整跑完，但不真的部署 Azure 資源。
"""

import argparse
import time
from pathlib import Path

from _common import config_path, load_json, print_header, print_step


# 步驟 1: 接受設定檔路徑，方便測試不同環境。
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulate Azure deployment for the Agent 365 lifecycle."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=config_path(),
        help="Path to a365.config.json.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # 步驟 2: 讀出部署目標，讓模擬輸出更接近真實流程。
    config = load_json(args.config)
    endpoint = config.get("botMessagingEndpoint") or config.get("messagingEndpoint")
    web_app_name = config.get("webAppName", "sample-agent-a365")

    print_header("Step 4 - Deploy")

    # 步驟 3: 這裡只保留教學節奏，不真的修改 Azure 環境。
    print_step("Cloud deployment is intentionally skipped for this repo.")
    time.sleep(0.5)
    print_step("Simulating Azure packaging...")
    time.sleep(0.5)
    print_step("Simulating Azure release pipeline...")
    time.sleep(0.5)
    print_step(
        f"Pretend deployment succeeded: Azure Web App '{web_app_name}' is serving {endpoint or 'the configured endpoint'}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())