"""Central loader/saver for core/fleet_config.json."""
from __future__ import annotations

import json
import os
import socket
import uuid
from copy import deepcopy

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "fleet_config.json")

DEFAULT_PEER_SYNC = {
    "enabled": False,
    "server_url": "http://127.0.0.1:3001",
    "transmit_telemetry": True,
    "transmit_video": False,
    "receive_peer_telemetry": True,
    "accept_remote_commands": False,
    "shared_secret": "",
    "station_display_name": "",
}

DEFAULT_AI_SAFETY = {
    "require_command_confirm": True,
    "enable_remote_pilot_bridge": False,
}


def _default_config() -> dict:
    hostname = socket.gethostname().split(".")[0].upper()
    session_suffix = str(uuid.uuid4())[:4].upper()
    default_id = f"GCS-{hostname}-{session_suffix}"
    return {
        "station_id": default_id,
        "station_name": default_id,
        "cesium_token": "",
        "peer_sync": deepcopy(DEFAULT_PEER_SYNC),
        "ai_safety": deepcopy(DEFAULT_AI_SAFETY),
    }


def load_fleet_config() -> dict:
    cfg = _default_config()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            cfg.update({k: v for k, v in loaded.items() if k not in ("peer_sync", "ai_safety")})
            if isinstance(loaded.get("peer_sync"), dict):
                cfg["peer_sync"].update(loaded["peer_sync"])
            if isinstance(loaded.get("ai_safety"), dict):
                cfg["ai_safety"].update(loaded["ai_safety"])
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"FleetConfig: load failed: {e}")

    # Env overrides for secrets / identity
    if os.getenv("GCS_STATION_ID"):
        cfg["station_id"] = os.environ["GCS_STATION_ID"]
    if os.getenv("GCS_STATION_NAME"):
        cfg["station_name"] = os.environ["GCS_STATION_NAME"]
    if os.getenv("CESIUM_ION_TOKEN"):
        cfg["cesium_token"] = os.environ["CESIUM_ION_TOKEN"]
    if os.getenv("GCS_PEER_SYNC_URL"):
        cfg["peer_sync"]["server_url"] = os.environ["GCS_PEER_SYNC_URL"]
    if os.getenv("GCS_PEER_SYNC_SECRET") is not None:
        cfg["peer_sync"]["shared_secret"] = os.environ["GCS_PEER_SYNC_SECRET"]

    return cfg


def save_fleet_config(cfg: dict) -> None:
    out = deepcopy(cfg)
    # Never serialize env-only overrides that operator typed into empty local token
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=4)


def get_peer_sync(cfg: dict | None = None) -> dict:
    if cfg is None:
        cfg = load_fleet_config()
    peer = deepcopy(DEFAULT_PEER_SYNC)
    peer.update(cfg.get("peer_sync") or {})
    return peer


def get_ai_safety(cfg: dict | None = None) -> dict:
    if cfg is None:
        cfg = load_fleet_config()
    safety = deepcopy(DEFAULT_AI_SAFETY)
    safety.update(cfg.get("ai_safety") or {})
    return safety
