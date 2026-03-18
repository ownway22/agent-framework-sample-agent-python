from __future__ import annotations

import argparse
import os
from pathlib import Path

from _common import (
    config_path,
    detect_az_login,
    fail,
    generated_config_path,
    load_env_file,
    load_json,
    print_header,
    print_step,
    require_command,
    run_command,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Agent 365 blueprint setup using the a365 CLI."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=config_path(),
        help="Path to a365.config.json.",
    )
    parser.add_argument(
        "--with-infrastructure",
        action="store_true",
        help="Create Azure infrastructure instead of skipping that phase.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the setup command without executing it.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Pass verbose logging to the a365 CLI.",
    )
    return parser.parse_args()


def try_existing_blueprint_fallback(config: dict[str, object]) -> bool:
    blueprint_id = str(
        os.getenv("AGENT_BLUEPRINT_ID")
        or config.get("agentBlueprintId")
        or ""
    ).strip()
    if not blueprint_id:
        blueprint_id = str(config.get("clientAppId") or "").strip()
    if not blueprint_id:
        return False

    app_result = run_command(
        ["az", "ad", "app", "show", "--id", blueprint_id, "--output", "json"],
        capture_output=True,
    )
    sp_result = run_command(
        ["az", "ad", "sp", "show", "--id", blueprint_id, "--output", "json"],
        capture_output=True,
    )
    if app_result.returncode != 0 or sp_result.returncode != 0:
        return False

    app_payload = load_json_from_text(app_result.stdout)
    sp_payload = load_json_from_text(sp_result.stdout)
    if not app_payload or not sp_payload:
        return False

    generated_payload = {
        "agentBlueprintId": app_payload.get("appId"),
        "agentBlueprintObjectId": app_payload.get("id"),
        "agentBlueprintServicePrincipalObjectId": sp_payload.get("id"),
        "agentBlueprintClientSecretProtected": bool(
            app_payload.get("passwordCredentials")
        ),
        "botMessagingEndpoint": config.get("botMessagingEndpoint")
        or config.get("messagingEndpoint"),
        "resourceConsents": [],
        "completed": True,
    }
    write_json(generated_config_path(), generated_payload)
    print_step(
        "a365 setup did not fully complete, but an existing blueprint was found in the tenant; wrote fallback a365.generated.config.json from that existing blueprint."
    )
    return True


def load_json_from_text(raw: str) -> dict[str, object]:
    import json

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def main() -> int:
    args = parse_args()
    load_env_file()
    config = load_json(args.config)

    print_header("Step 3 - Setup agent blueprint")

    try:
        require_command("az", "https://learn.microsoft.com/cli/azure/install-azure-cli")
        require_command("a365", "https://learn.microsoft.com/en-us/microsoft-agent-365/developer/agent-365-cli")
    except RuntimeError as exc:
        return fail(str(exc))

    if not args.config.exists():
        return fail(
            f"Missing config file: {args.config}. Run publishAgent/02_setup-a365-config.py first."
        )

    print_step("Running prerequisite validation via a365 setup requirements.")
    requirements = run_command(["a365", "setup", "requirements"], cwd=args.config.parent)
    if requirements.returncode != 0:
        print_step("Requirements check reported issues. Review the CLI output above.")
        if not detect_az_login():
            print_step("Azure CLI is not logged in. Run: az login")
        return requirements.returncode

    if not detect_az_login():
        return fail("Azure CLI is not logged in. Run 'az login' and retry.")

    if os.getenv("AGENT_BLUEPRINT_ID") and try_existing_blueprint_fallback(config):
        print_step(
            "Using the existing tenant blueprint referenced by AGENT_BLUEPRINT_ID; skipping a365 setup all."
        )
        return 0

    command = ["a365", "setup", "all", "--config", str(args.config)]
    if not args.with_infrastructure:
        command.append("--skip-infrastructure")
    if args.verbose:
        command.append("--verbose")
    if args.dry_run:
        command.append("--dry-run")

    print_step("Executing Agent 365 setup flow.")
    print_step("Command: " + " ".join(command))
    result = run_command(command, cwd=args.config.parent)
    if result.returncode != 0:
        if try_existing_blueprint_fallback(config):
            return 0
        return fail(
            "Agent blueprint setup failed. Check the a365 output above, especially consent and role errors.",
            result.returncode,
        )

    generated = generated_config_path()
    if generated.exists():
        print_step(f"Generated Agent 365 config is available: {generated}")
    else:
        print_step(
            "Setup completed but a365.generated.config.json was not found yet. Verify with 'a365 config display -g'."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())