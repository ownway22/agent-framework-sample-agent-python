from __future__ import annotations

import argparse
import time
from pathlib import Path

from _common import config_path, load_json, print_header, print_step


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
    config = load_json(args.config)
    endpoint = config.get("botMessagingEndpoint") or config.get("messagingEndpoint")
    web_app_name = config.get("webAppName", "sample-agent-a365")

    print_header("Step 4 - Deploy")
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