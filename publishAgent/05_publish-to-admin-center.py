from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from _common import (
    config_path,
    env_file_path,
    fail,
    generated_config_path,
    load_json,
    load_env_file,
    manifest_dir,
    print_header,
    print_step,
    require_command,
    repo_root,
    run_command,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package the agent for Microsoft 365 admin center upload."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=config_path(),
        help="Path to a365.config.json.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Pass --dry-run to a365 publish.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Pass verbose logging to a365 publish.",
    )
    return parser.parse_args()


def _load_manifest_template() -> dict[str, object] | None:
    template_path = repo_root() / "manifest-template.json"
    if not template_path.exists():
        return None
    return json.loads(template_path.read_text(encoding="utf-8"))


def _resolve_blueprint_id(config: dict[str, object], generated: dict[str, object]) -> str:
    candidates = [
        str(generated.get("agentBlueprintId") or "").strip(),
        str(config.get("clientAppId") or "").strip(),
        str(config.get("agentBlueprintId") or "").strip(),
    ]
    for candidate in candidates:
        if candidate:
            return candidate
    raise RuntimeError("Could not determine the agent blueprint ID for manifest generation.")


def _env_or_value(*keys: str, default: str = "") -> str:
    for key in keys:
        value = os.getenv(key)
        if value:
            return value.strip()
    return default


def ensure_manifest_assets(config: dict[str, object], generated: dict[str, object]) -> None:
    target = manifest_dir()
    target.mkdir(parents=True, exist_ok=True)

    color_icon = target / "color.png"
    outline_icon = target / "outline.png"
    preferred_icon = repo_root() / "images" / "agentframework-thumbnail.png"
    fallback_icon = repo_root() / "images" / "thumbnail.png"
    icon_source = preferred_icon if preferred_icon.exists() else fallback_icon

    if icon_source.exists():
        shutil.copyfile(icon_source, color_icon)
        shutil.copyfile(icon_source, outline_icon)

    manifest_path = target / "manifest.json"
    payload = _load_manifest_template() or load_json(manifest_path)
    if not payload:
        raise RuntimeError(
            "manifest-template.json is missing and there is no existing manifest/manifest.json to publish."
        )

    blueprint_id = _resolve_blueprint_id(config, generated)
    app_name = str(
        config.get("agentUserDisplayName")
        or payload.get("name", {}).get("full")
        or "Sample Agent"
    ).strip()
    short_description = _env_or_value(
        "A365_AGENT_SHORT_DESCRIPTION",
        "AGENT_SHORT_DESCRIPTION",
        default="Python sample agent built with Agent Framework and Microsoft Agent 365 SDK.",
    )
    full_description = _env_or_value(
        "A365_AGENT_FULL_DESCRIPTION",
        "AGENT_FULL_DESCRIPTION",
        default=(
            f"{app_name} is a Python sample agent built with Agent Framework and the Microsoft Agent 365 SDK. "
            "It demonstrates observability, notifications, MCP tool integration, and Microsoft 365 agent hosting patterns."
        ),
    )

    payload["id"] = blueprint_id
    developer = payload.setdefault("developer", {})
    payload.setdefault("name", {})
    payload.setdefault("description", {})
    payload.setdefault("icons", {})
    developer["name"] = _env_or_value(
        "A365_PUBLISHER_NAME",
        "PUBLISHER_NAME",
        default=str(developer.get("name") or "Frank Lin").strip(),
    )
    developer["websiteUrl"] = _env_or_value(
        "A365_PUBLISHER_WEBSITE_URL",
        "PUBLISHER_WEBSITE_URL",
        default=str(
            developer.get("websiteUrl")
            or "https://www.linkedin.com/in/yu-hong-frank-lin-97764856/"
        ).strip(),
    )
    developer["privacyUrl"] = _env_or_value(
        "A365_PRIVACY_URL",
        "PRIVACY_URL",
        default=str(
            developer.get("privacyUrl")
            or "https://www.microsoft.com/en-us/privacy/privacystatement"
        ).strip(),
    )
    developer["termsOfUseUrl"] = _env_or_value(
        "A365_TERMS_URL",
        "TERMS_OF_USE_URL",
        default=str(
            developer.get("termsOfUseUrl")
            or "https://learn.microsoft.com/en-us/legal/ai-code-of-conduct"
        ).strip(),
    )
    payload["icons"]["color"] = "color.png"
    payload["icons"]["outline"] = "outline.png"
    payload["name"]["full"] = app_name
    payload["name"]["short"] = app_name[:30]
    payload["description"]["short"] = short_description
    payload["description"]["full"] = full_description

    web_application = payload.setdefault("webApplicationInfo", {})
    web_application["id"] = blueprint_id
    web_application["resource"] = f"api://{blueprint_id}"

    bots = payload.setdefault("bots", [])
    if bots:
        bots[0]["botId"] = blueprint_id

    copilot_agents = payload.get("copilotAgents", {})
    custom_engine_agents = copilot_agents.get("customEngineAgents", [])
    if custom_engine_agents:
        custom_engine_agents[0]["id"] = blueprint_id

    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    agentic_template_path = target / "agenticUserTemplateManifest.json"
    if not agentic_template_path.exists():
        template_payload = {
            "id": blueprint_id,
            "name": app_name,
            "description": short_description,
        }
        agentic_template_path.write_text(
            json.dumps(template_payload, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> int:
    args = parse_args()
    load_env_file()

    print_header("Step 5 - Publish to Microsoft 365 admin center")

    try:
        require_command("a365", "https://learn.microsoft.com/en-us/microsoft-agent-365/developer/agent-365-cli")
    except RuntimeError as exc:
        return fail(str(exc))

    if not args.config.exists():
        return fail(
            f"Missing config file: {args.config}. Run publishAgent/02_setup-a365-config.py first."
        )
    if not generated_config_path().exists():
        return fail(
            "Missing a365.generated.config.json. Run publishAgent/03_setup-agent-blueprint.py first."
        )

    config = load_json(args.config)
    generated = load_json(generated_config_path())
    ensure_manifest_assets(config, generated)
    print_step(f"Manifest assets prepared in {manifest_dir()}")

    command = ["a365", "publish"]
    if args.verbose:
        command.append("--verbose")
    if args.dry_run:
        command.append("--dry-run")

    print_step("Running the Agent 365 publish command.")
    result = run_command(command, cwd=repo_root())
    if result.returncode != 0:
        return fail(
            "a365 publish failed. Review the CLI output above and adjust manifest metadata if needed.",
            result.returncode,
        )

    print_step("a365 publish completed.")
    print_step("Next manual step in Microsoft 365 admin center:")
    print_step("1. Open https://admin.microsoft.com/")
    print_step("2. Go to Agents > All agents > Upload custom agent")
    print_step("3. Upload manifest/manifest.zip and complete the approval flow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())