"""
Configuration and System Telemetry API Router.
Manages anti-ban safety presets, delay configurations, and system hardware diagnostics.
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Response

from config_manager import ConfigManager, BUILTIN_PRESETS
from backend.models import ConfigUpdateRequest, PresetApplyRequest
from backend.database import db
from device_manager import DeviceManager
from logger import get_logger

logger = get_logger("ConfigRouter")
router = APIRouter(prefix="/api/config", tags=["Configuration"])


@router.get("")
def get_configuration():
    """Retrieves current application settings and available anti-ban presets."""
    cfg = ConfigManager.load()
    return {
        "config": {
            "browser": cfg.browser,
            "min_delay": cfg.min_delay,
            "max_delay": cfg.max_delay,
            "batch_size": cfg.batch_size,
            "batch_pause": cfg.batch_pause,
            "daily_cap": cfg.daily_cap,
            "default_message": cfg.default_message,
            "default_country_code": cfg.default_country_code,
            "headless": cfg.headless,
            "active_preset": cfg.active_preset
        },
        "presets": BUILTIN_PRESETS
    }


@router.put("")
def update_configuration(payload: ConfigUpdateRequest):
    """Updates application settings with strict validation bounds and persists to disk."""
    cfg = ConfigManager.load()

    if payload.min_delay is not None:
        cfg.min_delay = payload.min_delay
    if payload.max_delay is not None:
        if payload.max_delay < cfg.min_delay:
            raise HTTPException(status_code=422, detail="max_delay cannot be less than min_delay")
        cfg.max_delay = payload.max_delay
    if payload.batch_size is not None:
        cfg.batch_size = payload.batch_size
    if payload.batch_pause is not None:
        cfg.batch_pause = payload.batch_pause
    if payload.daily_cap is not None:
        cfg.daily_cap = payload.daily_cap
    if payload.default_message is not None:
        cfg.default_message = payload.default_message
    if payload.default_country_code is not None:
        cfg.default_country_code = payload.default_country_code
    if payload.headless is not None:
        cfg.headless = payload.headless

    is_valid, errors = cfg.validate()
    if not is_valid:
        raise HTTPException(status_code=422, detail={"validation_errors": errors})

    ConfigManager.save(cfg)
    return {"success": True, "message": "Configuration updated successfully"}


@router.post("/preset")
def apply_preset(payload: PresetApplyRequest):
    """Applies a built-in safety preset (safe, balanced, or fast) and saves configuration."""
    preset_key = payload.preset_name.lower().strip()
    if preset_key not in BUILTIN_PRESETS:
        raise HTTPException(status_code=400, detail=f"Unknown preset '{preset_key}'. Available: {list(BUILTIN_PRESETS.keys())}")

    cfg = ConfigManager.load()
    success = cfg.apply_preset(preset_key)
    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to apply preset '{preset_key}'")

    ConfigManager.save(cfg)
    return {
        "success": True,
        "applied_preset": preset_key,
        "preset_details": BUILTIN_PRESETS[preset_key]
    }


@router.get("/system-info")
def get_system_hardware_info():
    """Retrieves hardware fingerprint, OS information, CPU, and RAM metrics."""
    try:
        dm = DeviceManager()
        info = dm.get_device_info()
        return {
            "device_id": info.get("device_id", "N/A"),
            "system": info.get("system", "Windows"),
            "node": info.get("node", "Localhost"),
            "release": info.get("release", ""),
            "version": info.get("version", ""),
            "machine": info.get("machine", "x86_64"),
            "processor": info.get("processor", "Unknown"),
            "ram_total_gb": round(info.get("ram_total", 0) / (1024**3), 1) if info.get("ram_total") else "N/A"
        }
    except Exception as e:
        logger.warning(f"Error reading system hardware info: {e}")
        return {"error": str(e)}


@router.get("/backup")
def export_application_backup():
    """Generates a complete JSON backup containing config, message templates, contact groups, and suppression list."""
    cfg = ConfigManager.load()
    templates = db.get_templates()
    groups = db.get_groups()
    suppression = db.get_suppression_list()

    backup_payload = {
        "version": "2.0",
        "created_at": datetime.now().isoformat(),
        "config": cfg.to_dict(),
        "templates": templates,
        "groups": groups,
        "suppression": suppression
    }

    dumped = json.dumps(backup_payload, indent=2)
    filename = f"whatsapp_tool_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return Response(
        content=dumped,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/restore")
async def restore_application_backup(file: UploadFile = File(...)):
    """Restores application configuration and templates from a validated JSON backup file."""
    contents = await file.read()
    try:
        data = json.loads(contents.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid backup file. Must be valid JSON.")

    if not isinstance(data, dict) or "config" not in data:
        raise HTTPException(status_code=400, detail="Malformed backup payload: missing 'config' block.")

    # 1. Restore Config
    try:
        cfg = ConfigManager.from_dict(data["config"])
        ConfigManager.save(cfg)
    except Exception as e:
        logger.warning(f"Error restoring config from backup: {e}")

    # 2. Restore Templates
    restored_templates = 0
    for t in data.get("templates", []):
        try:
            if t.get("name") and t.get("content"):
                db.add_template(name=t["name"], content=t["content"])
                restored_templates += 1
        except Exception:
            pass

    # 3. Restore Contact Groups
    restored_groups = 0
    for g in data.get("groups", []):
        try:
            if g.get("name"):
                db.add_group(name=g["name"], description=g.get("description", ""))
                restored_groups += 1
        except Exception:
            pass

    # 4. Restore Suppression
    restored_suppression = 0
    for s in data.get("suppression", []):
        try:
            if s.get("phone"):
                db.add_to_suppression_list(
                    phone=s["phone"],
                    reason=s.get("reason", "restored_backup"),
                    source=s.get("source", "backup_restore")
                )
                restored_suppression += 1
        except Exception:
            pass

    db.log_event("INFO", "Backup", f"Restored backup: {restored_templates} templates, {restored_groups} groups, {restored_suppression} suppressions.")
    return {
        "success": True,
        "message": f"Backup successfully restored: {restored_templates} templates, {restored_groups} groups.",
        "restored_templates": restored_templates,
        "restored_groups": restored_groups
    }
