# Project Architecture Map

## Overview
TrueGCS is a Ground Control Station for multi-drone ops, video/AI, and optional peer-GCS sync
via a Fleet Brain Socket.IO relay (`GCSManager`).

## Directory Structure & Responsibilities

| Directory | Responsibility |
| :--- | :--- |
| `core/` | Config, peer sync client, footprint geolocation, LLM client, model shield |
| `ui/` | PySide6 cockpit (ops/map/cesium/config tabs) |
| `video/` | GStreamer capture + YOLO inference |
| `telemetry/` | MAVLink multiplexing thread |
| `gimbal/` | Mount tracker for AI slewing |
| `GCSManager/` | Optional Node.js peer-sync relay (localhost by default) |
| `simulation/` | VTOL/quad SITL-style sims |
| `models/` | YOLO weights (`.tsm` shielded / `.tflite`) |

## Primary Entry Points

* Desktop GCS: `main.py`
* Peer sync relay: `GCSManager/server.js` (default `127.0.0.1:3001`)
* Simulation: `simulation/vtol_sim.py`, `simulation/quad_sim.py`

## Core Data Flows

### Command / Telemetry
`UI` ↔ `main.py` routers ↔ `telemetry/mavlink_thread.py` ↔ vehicles

### Peer GCS Sync (opt-in)
Config → **Peer GCS Sync** tab → `FleetBrainObserver` → `BrainClient` ↔ `GCSManager` ↔ peer TrueGCS

* **Transmit:** local telemetry (and optional video) when enabled
* **Receive:** peer telemetry plotted on map/cesium
* **Remote commands:** off by default (`accept_remote_commands`)

### Vision
`VideoThread` → YOLO → UI overlay / gimbal tracker (LLM is a separate chat path, not in the video hot path)

## Key Components

* `core/fleet_config.py` + `core/fleet_config.json` — station identity, peer sync, AI safety flags
* `core/fleet_brain_observer.py` — starts only when peer sync is enabled
* `core/camera_footprint_manager.py` — camera ground footprint / click-to-geo
* `core/llm_client.py` — tactical LLM; flight actions require operator confirm by default
