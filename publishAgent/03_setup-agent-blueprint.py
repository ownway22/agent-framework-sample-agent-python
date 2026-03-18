from __future__ import annotations

"""
步驟 1: 驗證 az 與 a365 CLI 環境。
步驟 2: 優先嘗試重用既有 blueprint。
步驟 3: 必要時再執行 a365 setup all。
"""

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from _common import (
    blueprint_metadata_path,
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


# 步驟 1: 收斂本腳本會用到的命令列參數。
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


# 步驟 2: 若租戶內已經有對應 blueprint，就直接回填 generated config。
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


# 步驟 3: 將 az CLI 回傳字串安全轉成 JSON。
def load_json_from_text(raw: str) -> dict[str, object]:
    import json

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


# 步驟 4: 將 setup 結果整理成較完整的 blueprint metadata，方便交接與追查。
def build_blueprint_metadata(
    config: dict[str, object],
    generated: dict[str, object],
    *,
    source: str,
) -> dict[str, object]:
    blueprint_id = str(generated.get("agentBlueprintId") or "").strip()
    validation_errors: list[str] = []
    required_fields = {
        "agentBlueprintId": blueprint_id,
        "agentBlueprintObjectId": str(generated.get("agentBlueprintObjectId") or "").strip(),
        "agentBlueprintServicePrincipalObjectId": str(
            generated.get("agentBlueprintServicePrincipalObjectId") or ""
        ).strip(),
        "tenantId": str(config.get("tenantId") or "").strip(),
        "subscriptionId": str(config.get("subscriptionId") or "").strip(),
        "resourceGroup": str(config.get("resourceGroup") or "").strip(),
        "location": str(config.get("location") or "").strip(),
        "botMessagingEndpoint": str(generated.get("botMessagingEndpoint") or "").strip(),
    }
    for field_name, field_value in required_fields.items():
        if not field_value:
            validation_errors.append(f"Missing required blueprint field: {field_name}")

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    existing_metadata = load_json(blueprint_metadata_path())
    existing_audit = existing_metadata.get("audit") if isinstance(existing_metadata.get("audit"), dict) else {}

    return {
        "schemaVersion": "1.0",
        "completed": bool(generated.get("completed")),
        "validationStatus": "passed" if not validation_errors else "warning",
        "validationErrors": validation_errors,
        "identity": {
            "agentBlueprintId": blueprint_id,
            "agentBlueprintObjectId": str(generated.get("agentBlueprintObjectId") or "").strip(),
            "agentBlueprintServicePrincipalObjectId": str(
                generated.get("agentBlueprintServicePrincipalObjectId") or ""
            ).strip(),
            "agentBlueprintDisplayName": str(config.get("agentBlueprintDisplayName") or "").strip(),
            "clientAppId": str(config.get("clientAppId") or "").strip(),
        },
        "environment": {
            "tenantId": str(config.get("tenantId") or "").strip(),
            "subscriptionId": str(config.get("subscriptionId") or "").strip(),
            "resourceGroup": str(config.get("resourceGroup") or "").strip(),
            "location": str(config.get("location") or "").strip(),
            "environment": str(config.get("environment") or "").strip(),
        },
        "runtime": {
            "webAppName": str(config.get("webAppName") or "").strip(),
            "appServicePlanName": str(config.get("appServicePlanName") or "").strip(),
            "appServicePlanSku": str(config.get("appServicePlanSku") or "").strip(),
            "botMessagingEndpoint": str(generated.get("botMessagingEndpoint") or "").strip(),
            "messagingEndpoint": str(config.get("messagingEndpoint") or config.get("botMessagingEndpoint") or "").strip(),
            "webApplicationResource": f"api://{blueprint_id}" if blueprint_id else "",
        },
        "agentProfile": {
            "agentUserDisplayName": str(config.get("agentUserDisplayName") or "").strip(),
            "agentUserPrincipalName": str(config.get("agentUserPrincipalName") or "").strip(),
            "agentDescription": str(config.get("agentDescription") or "").strip(),
            "managerEmail": str(config.get("managerEmail") or "").strip(),
        },
        "security": {
            "clientSecretProtected": bool(generated.get("agentBlueprintClientSecretProtected")),
            "resourceConsents": generated.get("resourceConsents")
            if isinstance(generated.get("resourceConsents"), list)
            else [],
        },
        "audit": {
            "source": source,
            "createdAt": str(existing_audit.get("createdAt") or now),
            "updatedAt": now,
            "createdBy": os.getenv("USER", "unknown"),
        },
    }


def write_blueprint_metadata(
    config: dict[str, object],
    generated: dict[str, object],
    *,
    source: str,
) -> None:
    metadata = build_blueprint_metadata(config, generated, source=source)
    write_json(blueprint_metadata_path(), metadata)
    print_step(f"Generated blueprint metadata is available: {blueprint_metadata_path()}")


def main() -> int:
    args = parse_args()
    load_env_file()

    print_header("Step 3 - Setup agent blueprint")

    if not args.config.exists():
        return fail(
            f"Missing config file: {args.config}. Run publishAgent/02_setup-a365-config.py first."
        )

    config = load_json(args.config)

    try:
        # 步驟 4: fallback 與正式流程都會用到 Azure CLI，因此先只檢查 az。
        require_command("az", "https://learn.microsoft.com/cli/azure/install-azure-cli")
    except RuntimeError as exc:
        return fail(str(exc))

    # 步驟 5: 若已指定既有 blueprint，先嘗試直接重用，避免卡在耗時 requirements。
    if os.getenv("AGENT_BLUEPRINT_ID"):
        if not detect_az_login():
            return fail("Azure CLI is not logged in. Run 'az login' and retry.")
        if try_existing_blueprint_fallback(config):
            generated = load_json(generated_config_path())
            write_blueprint_metadata(config, generated, source="existing-blueprint-fallback")
            print_step(
                "Using the existing tenant blueprint referenced by AGENT_BLUEPRINT_ID; skipped a365 setup requirements and a365 setup all."
            )
            return 0

    try:
        # 步驟 6: 只有在 fallback 不可用時，才需要 a365 CLI 進入正式 setup。
        require_command("a365", "https://learn.microsoft.com/en-us/microsoft-agent-365/developer/agent-365-cli")
    except RuntimeError as exc:
        return fail(str(exc))

    # 步驟 7: 先跑 requirements，提早看到權限與安裝問題。
    print_step("Running prerequisite validation via a365 setup requirements.")
    requirements = run_command(["a365", "setup", "requirements"], cwd=args.config.parent)
    if requirements.returncode != 0:
        print_step("Requirements check reported issues. Review the CLI output above.")
        if not detect_az_login():
            print_step("Azure CLI is not logged in. Run: az login")
        return requirements.returncode

    if not detect_az_login():
        return fail("Azure CLI is not logged in. Run 'az login' and retry.")

    # 步驟 8: 若 requirements 通過後才判定可重用 blueprint，仍可直接使用。
    if os.getenv("AGENT_BLUEPRINT_ID") and try_existing_blueprint_fallback(config):
        generated = load_json(generated_config_path())
        write_blueprint_metadata(config, generated, source="existing-blueprint-fallback")
        print_step(
            "Using the existing tenant blueprint referenced by AGENT_BLUEPRINT_ID; skipping a365 setup all."
        )
        return 0

    # 步驟 9: 找不到可重用 blueprint 時，才執行正式 setup 流程。
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

    # 步驟 10: 最後確認 generated config 是否真的產生。
    generated = generated_config_path()
    if generated.exists():
        write_blueprint_metadata(config, load_json(generated), source="a365-setup-all")
        print_step(f"Generated Agent 365 config is available: {generated}")
    else:
        print_step(
            "Setup completed but a365.generated.config.json was not found yet. Verify with 'a365 config display -g'."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())