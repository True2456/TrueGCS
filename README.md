# TrueGCS — ISR Ground Control Station

> A multi-drone, multi-link Ground Control Station built on MAVLink, PySide6, and YOLOv8.  
> Designed for VTOL fixed-wing platforms with tactical ISR mission support.

---

## Screenshots

> **To add your own screenshots:** drop `.png` / `.jpg` images into `docs/screenshots/` and they will render here on GitHub.

| Operations Tab | Video & Detection |
|:-:|:-:|
| ![Operations](docs/screenshots/ops_tab.png) | ![Video](docs/screenshots/video_tab.png) |

| Simulation Tab | Configuration Tab |
|:-:|:-:|
| ![Simulation](docs/screenshots/sim_tab.png) | ![Config](docs/screenshots/cfg_tab.png) |

---

## Features

### 🗺️ Operations
- **Live map** with offline tile server — works without internet
- **Drone icon** with real-time heading and position tracking
- **HUD overlay** — Speed, Altitude, Battery, Mode, EKF status, Lidar range
- **Sensor side panel** — GPS, GPS2/TRN, Lidar, EKF, Nav, Vision telemetry
- **Mission planner** — click-to-place waypoints, speed per waypoint, upload to drone
- **Takeoff / Start Mission** commands

### 📡 Multi-Node Telemetry
- **Unlimited concurrent drone links** — Serial, UDP, or TCP per node
- **Auto-discovery** — drones are detected from heartbeats, not configured manually
- **Color-coded nodes** — each link gets a unique colour assigned on first contact
- **Connection timeout guard** — failed links auto-clean after 5 seconds
- **Single-click disconnect** per node

### 🎥 Video & Detection
- UDP / RTMP / RTP / USB camera input
- **YOLOv8 / YOLOv8x / YOLO26 (1536px)** AI object detection
- **Click-to-track** — nearest detection, pixel seed, or centre slew modes
- Gimbal / mount control via MAVLink DO_MOUNT_CONTROL
- GPS-tagged target overlay on map

### 🛩️ Simulation
- Built-in **VTOL SITL simulator** (`simulation/vtol_sim.py`)
- Launch **multiple independent simulation instances** concurrently from the GCS UI
- Each sim runs on a configurable UDP port
- Live log streaming per instance
- Simulates: armed/disarmed state, waypoint navigation, VTOL transition, RTL, QRTL, loiter, GPS denial

### ⚙️ Configuration
- Full ArduPilot parameter browser — fetch, edit, and write parameters live
- **EnumSelector / BitmaskSelector** — curated dropdowns for known parameters
- Grouped parameter tree with 361 pre-loaded metadata groups
- Progress bar for full parameter list fetch

### 🎮 Flight Controls
- **Arm / Disarm** button with live state sync
- **Flight mode selector** — populated from vehicle's own mode map
- Arm state persisted per drone across multi-drone sessions

---

## Architecture

```
TrueGCS/
├── main.py                  # App entry point, signal wiring, node manager
├── ui/
│   ├── main_window.py       # Main window, connection bar, window geometry
│   ├── tabs_ops.py          # Operations tab (map, HUD, video controls)
│   ├── tabs_video.py        # Video & Detection tab
│   ├── tabs_cfg.py          # Configuration / parameter tab
│   ├── tabs_sim.py          # Simulation tab (multi-instance SITL launcher)
│   ├── hud_overlay.py       # Floating HUD and sensor panel widgets
│   ├── map_widget.py        # QWebEngineView map with Leaflet.js
│   └── styles.py            # Global QSS stylesheet
├── telemetry/
│   └── mavlink_thread.py    # MAVLink receive/transmit thread per node
├── video/
│   └── video_thread.py      # Video decode, YOLOv8 inference, gimbal control
├── gimbal/
│   └── mount_tracker.py     # PID-based gimbal tracking controller
├── simulation/
│   ├── vtol_sim.py          # VTOL SITL simulator (MAVLink 2.0 broadcast)
│   └── sim_config.json      # Simulator network/drone configuration
└── core/
    └── pid_controller.py    # Generic PID controller
```

---

## Requirements

| Dependency | Version |
|---|---|
| Python | ≥ 3.10 |
| PySide6 | ≥ 6.5.0 |
| pymavlink | ≥ 2.4.40 |
| opencv-python | ≥ 4.8.0 |
| ultralytics (YOLOv8) | ≥ 8.0.0 |
| numpy | ≥ 1.24.0 |
| requests | ≥ 2.31.0 |

---

## Installation

```bash
# Clone the repository
git clone https://github.com/True2456/TrueGCS.git
cd TrueGCS

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt
```

---

## Running

```bash
source venv/bin/activate && python main.py
```

---

## Connecting a Drone

1. Select your connection type in the top bar — **Serial**, **UDP**, or **TCP**
2. Set the baud rate (Serial) or port (UDP/TCP)
3. Click **+ Add** — the GCS will attempt to connect for 5 seconds
4. On success, the drone appears in the **Active Target** dropdown with its assigned colour
5. Arm, set mode, and fly

---

## Running the Simulation

### From the GCS UI (recommended)
1. Go to the **Simulation** tab
2. Set a UDP port (default `14550`)
3. Click **▶ Launch** — the sim starts broadcasting heartbeats
4. Switch to **Operations**, select **UDP** in the NODE bar, enter the same port, click **+ Add**
5. The simulated drone is discovered and appears on the map

### Multiple concurrent drones
1. Click **＋ Add Simulation** to add more instances (each needs a unique port)
2. Launch all instances, then add a matching UDP node for each in the connection bar

### From the terminal
```bash
source venv/bin/activate && python simulation/vtol_sim.py
# or on a custom port:
source venv/bin/activate && python simulation/vtol_sim.py --port 14551
```

---

## Adding Your Own Screenshots

1. Take screenshots of the running GCS
2. Save them to `docs/screenshots/` with these names:

| File | Tab |
|---|---|
| `docs/screenshots/ops_tab.png` | Operations (map view) |
| `docs/screenshots/video_tab.png` | Video & Detection |
| `docs/screenshots/sim_tab.png` | Simulation |
| `docs/screenshots/cfg_tab.png` | Configuration |

3. Commit and push — they will appear in this README automatically

---

## Platform Support

| Platform | Status |
|---|---|
| macOS (Apple Silicon / Intel) | ✅ Tested |
| Windows 10 / 11 | ✅ Tested |
| Linux (Ubuntu 22.04+) | ✅ Should work |

---

## License

Private repository — all rights reserved.
