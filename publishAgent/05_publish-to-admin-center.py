"""
步驟 1: 整理 manifest 內容與圖示檔案。
步驟 2: 每次自動提升 manifest 版本號。
步驟 3: 在 headless Linux 直接封裝 manifest.zip，不呼叫互動式 a365 publish。
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import struct
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4
import zlib

from _common import (
    blueprint_metadata_path,
    config_path,
    fail,
    generated_config_path,
    load_json,
    load_env_file,
    manifest_dir,
    print_header,
    print_step,
    repo_root,
)


COLOR_ICON_FILE_NAME = "color.png"
OUTLINE_ICON_FILE_NAME = "outline.png"
DEFAULT_VERSION = "1.0.1"
VERSION_EPOCH = date(2025, 1, 1)


# 步驟 1: 保留少量參數，讓腳本能用一般模式與 dry-run 模式共用。
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


# 步驟 2: 讀取 manifest template，作為每次產生 manifest 的基底。
def _load_manifest_template() -> dict[str, object] | None:
    template_path = repo_root() / "manifest-template.json"
    if not template_path.exists():
        return None
    return json.loads(template_path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_blueprint_metadata() -> dict[str, object]:
    return load_json(blueprint_metadata_path())


def _read_nested(payload: dict[str, object], *keys: str) -> str:
    current: object = payload
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return str(current or "").strip()


# 步驟 3: 從 metadata / generated config / config 中找出這次要寫入的 blueprint id。
def _resolve_blueprint_id(
    config: dict[str, object],
    generated: dict[str, object],
    metadata: dict[str, object],
) -> str:
    candidates = [
        _read_nested(metadata, "identity", "agentBlueprintId"),
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


def _resolve_package_id(dry_run: bool) -> str:
    configured = _env_or_value("A365_MANIFEST_PACKAGE_ID", "MANIFEST_PACKAGE_ID")
    if configured:
        return configured

    # 步驟 5: 每次正式封裝都使用新的 package/title id，避免撞到已部署的舊 title。
    return str(uuid4())


def _parse_version(raw: object) -> tuple[int, int, int] | None:
    if not isinstance(raw, str):
        return None
    parts = raw.strip().split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    major, minor, patch = (int(part) for part in parts)
    return major, minor, patch


# 步驟 4: 用 UTC 日期與秒數產生時間序版本，避免落回遠端舊版本之下。
def _time_ordered_version() -> tuple[int, int, int]:
    now = datetime.now(timezone.utc)
    days_since_epoch = (now.date() - VERSION_EPOCH).days
    seconds_since_midnight = now.hour * 3600 + now.minute * 60 + now.second
    return 1, days_since_epoch, seconds_since_midnight


def _next_manifest_version(*raw_versions: object) -> str:
    valid_versions = [parsed for raw in raw_versions if (parsed := _parse_version(raw))]
    default_version = _parse_version(DEFAULT_VERSION)
    assert default_version is not None

    candidate = _time_ordered_version()
    current = max(valid_versions + [default_version]) if valid_versions else default_version

    if candidate > current:
        major, minor, patch = candidate
        return f"{major}.{minor}.{patch}"

    major, minor, patch = current
    return f"{major}.{minor}.{patch + 1}"


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _write_rgba_png(path: Path, width: int, height: int, rows: list[bytes]) -> None:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    scanlines = b"".join(b"\x00" + row for row in rows)
    idat = zlib.compress(scanlines, level=9)
    png = signature + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", idat) + _png_chunk(b"IEND", b"")
    path.write_bytes(png)


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))


def _inside_rounded_rect(x: int, y: int, width: int, height: int, inset: int, radius: int) -> bool:
    left = inset
    top = inset
    right = width - inset - 1
    bottom = height - inset - 1
    if left > right or top > bottom:
        return False

    corner_x = _clamp(x, left + radius, right - radius)
    corner_y = _clamp(y, top + radius, bottom - radius)
    dx = x - corner_x
    dy = y - corner_y
    return dx * dx + dy * dy <= radius * radius


def _generate_color_icon(path: Path) -> None:
    width = 192
    height = 192
    rows: list[bytes] = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            if not _inside_rounded_rect(x, y, width, height, inset=8, radius=36):
                row.extend((0, 0, 0, 0))
                continue

            blue = 210 + (x * 20 // width)
            green = 88 + (y * 32 // height)
            red = 43 + ((x + y) * 14 // (width + height))

            if (x - 96) ** 2 + (y - 82) ** 2 <= 34 ** 2:
                row.extend((255, 255, 255, 255))
            elif 68 <= x <= 124 and 108 <= y <= 124:
                row.extend((255, 255, 255, 255))
            elif (x - 96) ** 2 + (y - 126) ** 2 <= 14 ** 2:
                row.extend((255, 255, 255, 255))
            else:
                row.extend((red, green, blue, 255))
        rows.append(bytes(row))
    _write_rgba_png(path, width, height, rows)


def _generate_outline_icon(path: Path) -> None:
    width = 32
    height = 32
    rows: list[bytes] = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            outer = _inside_rounded_rect(x, y, width, height, inset=1, radius=6)
            inner = _inside_rounded_rect(x, y, width, height, inset=4, radius=4)
            dot = (x - 16) ** 2 + (y - 12) ** 2 <= 4 ** 2
            stem = 14 <= x <= 18 and 16 <= y <= 23
            if (outer and not inner) or dot or stem:
                row.extend((255, 255, 255, 255))
            else:
                row.extend((0, 0, 0, 0))
        rows.append(bytes(row))
    _write_rgba_png(path, width, height, rows)


def _prepare_manifest_icons(target: Path, dry_run: bool) -> None:
    if dry_run:
        return

    _generate_color_icon(target / COLOR_ICON_FILE_NAME)
    _generate_outline_icon(target / OUTLINE_ICON_FILE_NAME)

    for stale_name in ("boy.png", "color32x32.png"):
        stale_path = target / stale_name
        if stale_path.exists():
            stale_path.unlink()


def _persist_template_settings(
    template_payload: dict[str, object],
    package_id: str,
    version: str,
    dry_run: bool,
) -> None:
    template_payload["id"] = package_id
    template_payload["version"] = version
    template_payload.setdefault("icons", {})
    template_payload["icons"]["color"] = COLOR_ICON_FILE_NAME
    template_payload["icons"]["outline"] = OUTLINE_ICON_FILE_NAME
    if not dry_run:
        _write_json(repo_root() / "manifest-template.json", template_payload)


def _package_manifest_zip(payload: dict[str, object], dry_run: bool) -> list[str]:
    target = manifest_dir()
    zip_path = target / "manifest.zip"
    icon_files = {
        str(value)
        for value in payload.get("icons", {}).values()
        if isinstance(value, str) and value.strip()
    }
    package_members = ["manifest.json"]
    if (target / "agenticUserTemplateManifest.json").exists():
        package_members.append("agenticUserTemplateManifest.json")
    package_members.extend(sorted(icon_files))

    if dry_run:
        return package_members

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member in package_members:
            archive.write(target / member, arcname=member)
    return package_members


def _write_manifest_metadata_snapshot(
    metadata: dict[str, object],
    *,
    dry_run: bool,
) -> Path | None:
    if not metadata:
        return None
    snapshot_path = manifest_dir() / "agent-blueprint.metadata.json"
    if not dry_run:
        _write_json(snapshot_path, metadata)
    return snapshot_path


def ensure_manifest_assets(
    config: dict[str, object],
    generated: dict[str, object],
    metadata: dict[str, object],
    *,
    dry_run: bool,
) -> dict[str, object]:
    target = manifest_dir()
    target.mkdir(parents=True, exist_ok=True)

    manifest_path = target / "manifest.json"
    template_payload = _load_manifest_template()
    existing_manifest = load_json(manifest_path)
    payload = copy.deepcopy(template_payload) if template_payload else load_json(manifest_path)
    if not payload:
        raise RuntimeError(
            "manifest-template.json is missing and there is no existing manifest/manifest.json to publish."
        )

    package_id = _resolve_package_id(dry_run)
    next_version = _next_manifest_version(
        template_payload.get("version") if template_payload else None,
        existing_manifest.get("version"),
    )
    if template_payload:
        _persist_template_settings(template_payload, package_id, next_version, dry_run)

    _prepare_manifest_icons(target, dry_run)

    blueprint_id = _resolve_blueprint_id(config, generated, metadata)
    app_name = str(
        config.get("agentUserDisplayName")
        or _read_nested(metadata, "agentProfile", "agentUserDisplayName")
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
            _read_nested(metadata, "agentProfile", "agentDescription")
            or (
                f"{app_name} is a Python sample agent built with Agent Framework and the Microsoft Agent 365 SDK. "
                "It demonstrates observability, notifications, MCP tool integration, and Microsoft 365 agent hosting patterns."
            )
        ),
    )

    payload["version"] = next_version
    payload["id"] = package_id
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
    payload["icons"]["color"] = COLOR_ICON_FILE_NAME
    payload["icons"]["outline"] = OUTLINE_ICON_FILE_NAME
    payload["name"]["full"] = app_name
    payload["name"]["short"] = app_name[:30]
    payload["description"]["short"] = short_description
    payload["description"]["full"] = full_description

    publisher_mpn_id = _env_or_value(
        "A365_PUBLISHER_MPN_ID",
        "PUBLISHER_MPN_ID",
    )
    if publisher_mpn_id.isdigit():
        payload.setdefault("developer", {})
        payload["developer"]["mpnId"] = publisher_mpn_id
    else:
        developer.pop("mpnId", None)

    web_application = payload.setdefault("webApplicationInfo", {})
    web_application["id"] = blueprint_id
    web_application["resource"] = (
        _read_nested(metadata, "runtime", "webApplicationResource")
        or f"api://{blueprint_id}"
    )

    bots = payload.setdefault("bots", [])
    if bots:
        bots[0]["botId"] = blueprint_id

    copilot_agents = payload.get("copilotAgents", {})
    custom_engine_agents = copilot_agents.get("customEngineAgents", [])
    if custom_engine_agents:
        custom_engine_agents[0]["id"] = blueprint_id

    if not dry_run:
        _write_json(manifest_path, payload)

    agentic_template_path = target / "agenticUserTemplateManifest.json"
    agentic_payload = {
            "id": package_id,
            "name": app_name,
            "description": short_description,
        }
    if not dry_run:
        _write_json(agentic_template_path, agentic_payload)

    return payload


def main() -> int:
    args = parse_args()
    load_env_file()

    print_header("Step 5 - Publish to Microsoft 365 admin center")

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
    metadata = _load_blueprint_metadata()
    
    # 步驟 4: 直接在本機產生 manifest 與 zip，避免 headless Linux 卡在互動式流程。
    payload = ensure_manifest_assets(config, generated, metadata, dry_run=args.dry_run)
    metadata_snapshot = _write_manifest_metadata_snapshot(metadata, dry_run=args.dry_run)
    package_members = _package_manifest_zip(payload, dry_run=args.dry_run)

    print_step(f"Manifest package ID prepared: {payload['id']}")
    print_step(f"Manifest version prepared: {payload['version']}")
    print_step(
        f"Manifest icons prepared: {COLOR_ICON_FILE_NAME} (192x192), {OUTLINE_ICON_FILE_NAME} (32x32)"
    )
    if metadata:
        print_step(
            "Blueprint metadata loaded: "
            f"status={_read_nested(metadata, 'validationStatus') or 'unknown'}, "
            f"source={_read_nested(metadata, 'audit', 'source') or 'unknown'}"
        )
        if metadata_snapshot is not None:
            print_step(f"Blueprint metadata snapshot prepared: {metadata_snapshot}")
    if args.dry_run:
        print_step(f"Dry run package members: {', '.join(package_members)}")
        print_step("Dry run completed. No files were written.")
        return 0

    print_step(f"Manifest assets prepared in {manifest_dir()}")
    print_step(f"Non-interactive package created: {manifest_dir() / 'manifest.zip'}")
    print_step("Next manual step in Microsoft 365 admin center:")
    print_step("1. Open https://admin.microsoft.com/")
    print_step("2. Go to Agents > All agents > Upload custom agent")
    print_step("3. Upload manifest/manifest.zip and complete the approval flow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())