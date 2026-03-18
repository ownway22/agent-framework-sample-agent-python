from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import (
    bool_from_env,
    config_path,
    is_guid,
    load_json,
    load_env_file,
    print_header,
    print_step,
    prompt_value,
    repo_root,
    slugify,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or update a365.config.json for this repo."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=config_path(),
        help="Target a365.config.json path.",
    )
    return parser.parse_args()


def load_manifest_client_app_id() -> str | None:
    template_path = repo_root() / "manifest-template.json"
    if not template_path.exists():
        return None
    try:
        payload = json.loads(template_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    manifest_id = payload.get("id")
    return manifest_id if isinstance(manifest_id, str) else None


def main() -> int:
    args = parse_args()
    load_env_file()
    root = repo_root()
    manifest_client_app_id = load_manifest_client_app_id()
    project_slug = slugify(root.name)
    project_name = root.name.replace("-", " ").strip()
    default_agent_name = " ".join(part.capitalize() for part in project_slug.split("-"))

    print_header("Step 2 - Setup Agent 365 config")

    existing = load_json(args.config)

    tenant_id = prompt_value(
        ["A365_TENANT_ID", "TENANT_ID", "AZURE_TENANT_ID"],
        "Tenant ID",
        default=existing.get("tenantId"),
        required=True,
        validator=is_guid,
    )
    subscription_id = prompt_value(
        ["A365_SUBSCRIPTION_ID", "SUBSCRIPTION_ID", "AZURE_SUBSCRIPTION_ID"],
        "Azure subscription ID",
        default=existing.get("subscriptionId"),
        required=True,
        validator=is_guid,
    )
    endpoint = prompt_value(
        [
            "A365_AGENT_ENDPOINT",
            "AGENT_MESSAGING_ENDPOINT",
            "BOT_MESSAGING_ENDPOINT",
            "MESSAGING_ENDPOINT",
        ],
        "Agent messaging endpoint",
        default=existing.get("botMessagingEndpoint")
        or existing.get("messagingEndpoint")
        or "https://your-agent-endpoint.example.com/api/messages",
        required=True,
    )

    environment = prompt_value(
        ["A365_ENVIRONMENT", "ENVIRONMENT"],
        "Environment name",
        default=existing.get("environment", "prod"),
        required=True,
    )
    location = prompt_value(
        ["A365_LOCATION", "AZURE_LOCATION", "LOCATION"],
        "Azure location",
        default=existing.get("location", "eastus"),
        required=True,
    )
    resource_group = prompt_value(
        ["A365_RESOURCE_GROUP", "AZURE_RESOURCE_GROUP", "RESOURCE_GROUP"],
        "Azure resource group",
        default=existing.get("resourceGroup", f"rg-{project_slug}-a365"),
        required=True,
    )
    app_service_plan_name = prompt_value(
        ["A365_APP_SERVICE_PLAN_NAME"],
        "App Service Plan name",
        default=existing.get("appServicePlanName", f"asp-{project_slug}-a365"),
        required=True,
    )
    app_service_plan_sku = prompt_value(
        ["A365_APP_SERVICE_PLAN_SKU"],
        "App Service Plan SKU",
        default=existing.get("appServicePlanSku", "B1"),
        required=True,
    )
    web_app_name = prompt_value(
        ["A365_WEB_APP_NAME"],
        "Azure Web App name",
        default=existing.get("webAppName", f"web-{project_slug}-a365"),
        required=True,
    )
    manager_email = prompt_value(
        ["A365_MANAGER_EMAIL", "MANAGER_EMAIL"],
        "Manager email",
        default=existing.get("managerEmail"),
        required=True,
    )
    client_app_id = prompt_value(
        [
            "A365_CLIENT_APP_ID",
            "CLIENT_APP_ID",
            "AGENT_BLUEPRINT_ID",
        ],
        "Custom client app registration ID",
        default=existing.get("clientAppId") or manifest_client_app_id,
        required=True,
        validator=is_guid,
    )
    agent_display_name = prompt_value(
        ["A365_AGENT_DISPLAY_NAME", "AGENT_DISPLAY_NAME", "AGENT_NAME"],
        "Agent display name",
        default=existing.get("agentUserDisplayName", default_agent_name),
        required=True,
    )
    agent_identity_display_name = prompt_value(
        ["A365_AGENT_IDENTITY_DISPLAY_NAME"],
        "Agent identity display name",
        default=existing.get(
            "agentIdentityDisplayName", f"{agent_display_name} Identity"
        ),
        required=True,
    )
    blueprint_display_name = prompt_value(
        ["A365_AGENT_BLUEPRINT_DISPLAY_NAME", "AGENT_BLUEPRINT_DISPLAY_NAME"],
        "Agent blueprint display name",
        default=existing.get(
            "agentBlueprintDisplayName", f"{agent_display_name} Blueprint"
        ),
        required=True,
    )
    agent_user_upn = prompt_value(
        ["A365_AGENT_USER_PRINCIPAL_NAME", "AGENT_USER_PRINCIPAL_NAME"],
        "Agent user principal name",
        default=existing.get(
            "agentUserPrincipalName", f"{project_slug}.agent@yourtenant.onmicrosoft.com"
        ),
        required=True,
    )
    usage_location = prompt_value(
        ["A365_AGENT_USER_USAGE_LOCATION", "AGENT_USER_USAGE_LOCATION"],
        "Agent user usage location",
        default=existing.get("agentUserUsageLocation", "US"),
        required=True,
    )
    need_deployment = bool_from_env(["A365_NEED_DEPLOYMENT", "NEED_DEPLOYMENT"], False)

    payload = dict(existing)
    payload.update(
        {
            "tenantId": tenant_id,
            "subscriptionId": subscription_id,
            "resourceGroup": resource_group,
            "location": location,
            "environment": environment,
            "needDeployment": need_deployment,
            "clientAppId": client_app_id,
            "appServicePlanName": app_service_plan_name,
            "appServicePlanSku": app_service_plan_sku,
            "webAppName": web_app_name,
            "agentIdentityDisplayName": agent_identity_display_name,
            "agentBlueprintDisplayName": blueprint_display_name,
            "agentUserPrincipalName": agent_user_upn,
            "agentUserDisplayName": agent_display_name,
            "managerEmail": manager_email,
            "agentUserUsageLocation": usage_location,
            "deploymentProjectPath": str(root),
            "agentDescription": existing.get(
                "agentDescription", f"{project_name} - Agent 365 Agent"
            ),
            "botMessagingEndpoint": endpoint,
            "messagingEndpoint": endpoint,
        }
    )

    args.config.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.config, payload)

    print_step(f"Wrote Agent 365 configuration to {args.config}")
    print_step(f"tenantId={tenant_id}")
    print_step(f"subscriptionId={subscription_id}")
    print_step(f"botMessagingEndpoint={endpoint}")
    print_step(
        "If you plan to run real Agent 365 setup next, authenticate first with: az login"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())