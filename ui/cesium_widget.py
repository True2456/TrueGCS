"""
CesiumWidget — 3D Terrain Globe for TrueGCS.

Renders a dark-themed, military-style 3D globe using CesiumJS 1.116+.
Drone positions are bridged from the telemetry system via update_drone_position().
"""

import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QDialog, QDialogButtonBox, QFrame
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, Qt, Signal, QObject, Slot
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebChannel import QWebChannel

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "core", "fleet_config.json")


def _load_token():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f).get("cesium_token", "")
    except Exception:
        return ""


def _save_token(token: str):
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    cfg["cesium_token"] = token.strip()
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=4)


# ──────────────────────────────────────────────
# Token setup dialog
# ──────────────────────────────────────────────
class CesiumTokenDialog(QDialog):
    """Prompt the operator to enter / update their Cesium Ion access token."""

    def __init__(self, current_token="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cesium Ion Token")
        self.setMinimumWidth(520)
        self.setStyleSheet("""
            QDialog { background: #090e11; color: #92b0c3; }
            QLabel  { color: #92b0c3; font-size: 12px; }
            QLineEdit {
                background: #060c11; color: #00ddff;
                border: 1px solid rgba(0,221,255,0.3);
                border-radius: 4px; padding: 6px; font-size: 12px;
            }
            QPushButton {
                background: rgba(0,221,255,0.12); color: #00ddff;
                border: 1px solid rgba(0,221,255,0.35);
                border-radius: 4px; padding: 6px 16px; font-weight: bold;
            }
            QPushButton:hover { background: rgba(0,221,255,0.25); }
        """)

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 20, 20, 20)

        title = QLabel("🌐  Cesium Ion Access Token")
        title.setStyleSheet("color:#00ddff; font-size:15px; font-weight:bold; letter-spacing:1px;")
        lay.addWidget(title)

        info = QLabel(
            "Create a free account at <b style='color:#00ddff'>cesium.com</b> to obtain your token.<br>"
            "The token is stored locally in <code>core/fleet_config.json</code> and remembered between sessions."
        )
        info.setWordWrap(True)
        info.setOpenExternalLinks(True)
        lay.addWidget(info)

        self.txt_token = QLineEdit(current_token)
        self.txt_token.setPlaceholderText("Paste your Cesium Ion JWT token here…")
        lay.addWidget(self.txt_token)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.setStyleSheet("QPushButton { min-width: 80px; }")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def token(self) -> str:
        return self.txt_token.text().strip()


# ──────────────────────────────────────────────
# JS to Python Bridge
# ──────────────────────────────────────────────
class CesiumBridge(QObject):
    footprint_toggle_requested = Signal(str)
    takeoff_requested = Signal(str)
    start_mission_requested = Signal(str)

    @Slot(str)
    def on_footprint_toggle(self, target_id):
        self.footprint_toggle_requested.emit(target_id)

    @Slot(str)
    def on_takeoff_request(self, target_id):
        self.takeoff_requested.emit(target_id)

    @Slot(str)
    def on_start_mission_request(self, target_id):
        self.start_mission_requested.emit(target_id)


# ──────────────────────────────────────────────
# Main Cesium 3D Widget
# ──────────────────────────────────────────────
class CesiumWidget(QWidget):
    """A 3D terrain globe rendered via CesiumJS inside a QWebEngineView."""

    token_changed = Signal(str)
    footprint_toggle_requested = Signal(str)
    takeoff_requested = Signal(str)
    start_mission_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._token = _load_token()
        self._active_fp_target = None
        self._setup_ui()

    # ── UI ────────────────────────────────────
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        bar = QFrame()
        bar.setFixedHeight(36)
        bar.setStyleSheet(
            "background: rgba(9,21,28,0.97); border-bottom: 1px solid rgba(0,221,255,0.2);"
        )
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(10, 0, 10, 0)

        lbl = QLabel("⬡  3D TERRAIN VIEW")
        lbl.setStyleSheet("color:#00ddff; font-weight:bold; letter-spacing:2px; font-size:11px;")
        bar_lay.addWidget(lbl)
        bar_lay.addStretch()

        self.btn_token = QPushButton("⚙  CONFIGURE TOKEN")
        self.btn_token.setStyleSheet(
            "QPushButton { background:rgba(0,221,255,0.1); color:#00ddff;"
            "border:1px solid rgba(0,221,255,0.3); border-radius:4px; padding:4px 12px;"
            "font-size:10px; font-weight:bold; letter-spacing:1px; }"
            "QPushButton:hover { background:rgba(0,221,255,0.2); }"
        )
        self.btn_token.clicked.connect(self._configure_token)
        bar_lay.addWidget(self.btn_token)

        root.addWidget(bar)

        # WebView
        self._web = QWebEngineView()
        self._web.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self._web.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self._web.settings().setAttribute(
            QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True
        )
        
        self._bridge = CesiumBridge()
        self._bridge.footprint_toggle_requested.connect(self.footprint_toggle_requested.emit)
        self._bridge.takeoff_requested.connect(self.takeoff_requested.emit)
        self._bridge.start_mission_requested.connect(self.start_mission_requested.emit)
        self._channel = QWebChannel()
        self._channel.registerObject("bridge", self._bridge)
        self._web.page().setWebChannel(self._channel)
        
        root.addWidget(self._web)

        # No-token placeholder
        self._placeholder = QLabel(
            "🌐  No Cesium Ion token configured.\n\nClick  ⚙ CONFIGURE TOKEN  to enter your free token."
        )
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet("color:#92b0c3; font-size:14px; background:#090e11;")
        self._placeholder.setVisible(False)
        root.addWidget(self._placeholder)

        self._load_cesium()

    def _load_cesium(self):
        if not self._token:
            self._web.setVisible(False)
            self._placeholder.setVisible(True)
            return
        self._placeholder.setVisible(False)
        self._web.setVisible(True)
        html = self._build_html(self._token)
        # Use cesium.com as base URL so CDN relative paths resolve correctly
        self._web.setHtml(html, QUrl("https://cesium.com/"))

    # ── Token management ──────────────────────
    def _configure_token(self):
        dlg = CesiumTokenDialog(self._token, self)
        if dlg.exec() == QDialog.Accepted:
            new_token = dlg.token()
            if new_token:
                self._token = new_token
                _save_token(new_token)
                self.token_changed.emit(new_token)
                self._load_cesium()

    # ── Python → JS bridge ───────────────────
    def update_drone_position(self, node_id, sysid, lat, lon, alt_agl, heading_deg, color="#00ddff"):
        """Push a drone's position into the 3D globe."""
        if not self._token or not self._web.isVisible():
            return
        label = f"Drone {node_id}:{sysid}"
        safe_color = str(color).replace("'", "")
        js = (
            f"if(typeof updateDrone!=='undefined'){{"
            f"updateDrone('{node_id}_{sysid}',{lat},{lon},{alt_agl},{heading_deg},'{safe_color}','{label}');"
            f"}}"
        )
        self._web.page().runJavaScript(js)

    def fly_to(self, lat, lon, alt=500):
        """Animate the camera to a position."""
        js = f"if(typeof flyTo!=='undefined')flyTo({lat},{lon},{alt});"
        self._web.page().runJavaScript(js)

    def add_target_marker(self, lat, lon, label="ISR TARGET"):
        """Drop an AI geolocation pin on the 3D globe."""
        safe = str(label).replace("'", "\\'")
        js = f"if(typeof addTargetMarker!=='undefined')addTargetMarker({lat},{lon},'{safe}');"
        self._web.page().runJavaScript(js)

    # ── Footprints & Video ───────────────────
    def add_footprint(self, node_id, sysid, corners, area_m2):
        """Add/update a camera footprint polygon on the 3D globe."""
        if not corners or len(corners) < 3 or not self._web.isVisible():
            return
        corners_str = "[" + ",".join(f"[{c[0]},{c[1]}]" for c in corners) + "]"
        js = f"if(typeof updateFootprint!=='undefined')updateFootprint('{node_id}_{sysid}', {corners_str});"
        self._web.page().runJavaScript(js)

    def clear_footprint(self, node_id, sysid):
        """Clear footprint overlay."""
        js = f"if(typeof clearFootprint!=='undefined')clearFootprint('{node_id}_{sysid}');"
        self._web.page().runJavaScript(js)

    def update_footprint_video_bytes(self, node_id, jpeg_bytes):
        """Update the video frame for the active footprint over 3D terrain."""
        # Only process if this widget is actually on screen to save CPU/GPU
        if not self._web.isVisible() or not self._active_fp_target:
            return
            
        import base64
        encoded = base64.b64encode(jpeg_bytes).decode('ascii')
        safe_encoded = encoded.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "")
        js = f"if(typeof updateFootprintVideo!=='undefined')updateFootprintVideo('{safe_encoded}');"
        self._web.page().runJavaScript(js)

    # ── HTML ─────────────────────────────────
    def _build_html(self, token: str) -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>TrueGCS 3D Terrain</title>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="https://cesium.com/downloads/cesiumjs/releases/1.116/Build/Cesium/Cesium.js"></script>
<link href="https://cesium.com/downloads/cesiumjs/releases/1.116/Build/Cesium/Widgets/widgets.css" rel="stylesheet">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body, #cesiumContainer {{ width:100%; height:100%; background:#000; overflow:hidden; }}
  #hud {{
    position:absolute; top:10px; left:10px;
    background:rgba(9,21,28,0.82);
    border:1px solid rgba(0,221,255,0.25);
    border-radius:6px; padding:8px 14px;
    color:#92b0c3; font:11px/1.6 monospace;
    pointer-events:none; z-index:10;
    min-width:160px;
  }}
  #hud .title {{
    color:#00ddff; font-weight:bold; letter-spacing:2px;
    border-bottom:1px solid rgba(0,221,255,0.2);
    margin-bottom:4px; padding-bottom:4px; font-size:10px;
  }}
  #droneCount {{ color:#00ff78; font-weight:bold; }}

  /* Custom drone popup */
  #dronePopup {{
    display:none; position:absolute; z-index:9999;
    background:rgba(9,21,28,0.95);
    border:1px solid rgba(0,221,255,0.4);
    border-radius:6px; padding:12px 14px;
    min-width:180px; font-family:monospace;
    box-shadow: 0 4px 20px rgba(0,0,0,0.6), 0 0 15px rgba(0,221,255,0.15);
    backdrop-filter: blur(8px);
  }}
  #dronePopup .popup-title {{
    color:#00ddff; font-weight:bold; font-size:12px;
    letter-spacing:1px; margin-bottom:8px;
    border-bottom:1px solid rgba(0,221,255,0.3);
    padding-bottom:6px;
  }}
  #dronePopup .popup-btn {{
    display:block; width:100%; padding:8px; margin-top:4px;
    cursor:pointer; border-radius:4px; font-weight:bold;
    font-size:11px; font-family:monospace; text-align:center;
    letter-spacing:0.5px; transition:all 0.15s;
  }}
  .popup-btn-takeoff {{
    background:rgba(0,221,255,0.15); border:1px solid rgba(0,221,255,0.4);
    color:#00ddff;
  }}
  .popup-btn-takeoff:hover {{ background:rgba(0,221,255,0.3); }}
  .popup-btn-auto {{
    background:rgba(51,255,85,0.12); border:1px solid rgba(51,255,85,0.35);
    color:#33ff55;
  }}
  .popup-btn-auto:hover {{ background:rgba(51,255,85,0.25); }}
  .popup-btn-fp {{
    background:rgba(255,170,0,0.15); border:1px solid rgba(255,170,0,0.4);
    color:#ffaa00;
  }}
  .popup-btn-fp:hover {{ background:rgba(255,170,0,0.3); }}
  .popup-btn-fp.active {{
    background:rgba(255,170,0,0.4); border-color:#ffcc00; color:#ffcc00;
  }}
</style>
</head>
<body>
<div id="cesiumContainer"></div>
<div id="hud">
  <div class="title">TRUEGCS &middot; 3D TERRAIN</div>
  <div>DRONES: <span id="droneCount">0</span></div>
</div>
<div id="dronePopup">
  <div class="popup-title" id="popupTitle">DRONE</div>
  <button class="popup-btn popup-btn-takeoff" id="popupTakeoff">TAKEOFF</button>
  <button class="popup-btn popup-btn-auto" id="popupAuto">AUTO MODE</button>
  <button class="popup-btn popup-btn-fp" id="popupFP">📷 FOOTPRINT OFF</button>
</div>
<script>
Cesium.Ion.defaultAccessToken = '{token}';

(async function() {{
  try {{
    const viewer = new Cesium.Viewer('cesiumContainer', {{
      terrain:              Cesium.Terrain.fromWorldTerrain({{
        requestVertexNormals: true,
        requestWaterMask:     true,
      }}),
      baseLayerPicker:      false,
      geocoder:             false,
      homeButton:           false,
      sceneModePicker:      false,
      navigationHelpButton: false,
      animation:            false,
      timeline:             false,
      fullscreenButton:     false,
      infoBox:              false,
      selectionIndicator:   true,
      skyAtmosphere:        new Cesium.SkyAtmosphere(),
    }});

    window._viewer = viewer;

    // Cesium World Imagery (Ion asset 2 = Bing aerial)
    viewer.imageryLayers.removeAll();
    viewer.imageryLayers.addImageryProvider(
      await Cesium.IonImageryProvider.fromAssetId(2)
    );

    viewer.scene.globe.enableLighting       = true;
    viewer.scene.globe.showGroundAtmosphere = true;
    viewer.scene.fog.enabled                = true;
    viewer.scene.fog.density                = 0.0003;

    // Start with a global overview
    viewer.camera.setView({{
      destination: Cesium.Cartesian3.fromDegrees(0, 0, 20000000),
    }});

    const drones = {{}};
    let droneCount = 0;
    const aiTargets = [];
    const footprintPolygons = {{}};
    const footprintMaterials = {{}};
    const videoCanvases = {{}};
    const activeCanvasIdx = {{}};
    
    // Set up QWebChannel connection
    new QWebChannel(qt.webChannelTransport, function(channel) {{
        window.bridge = channel.objects.bridge;
    }});

    // ── Custom Drone Popup ───────────────────────────────────────
    const popup = document.getElementById('dronePopup');
    const popupTitle = document.getElementById('popupTitle');
    const popupTakeoff = document.getElementById('popupTakeoff');
    const popupAuto = document.getElementById('popupAuto');
    const popupFP = document.getElementById('popupFP');
    let currentPopupTarget = null;
    const fpActiveState = {{}};

    function showDronePopup(targetId, label, screenX, screenY) {{
      currentPopupTarget = targetId;
      popupTitle.textContent = label || ('DRONE ' + targetId);

      // Update FP button text
      const isActive = fpActiveState[targetId] || false;
      popupFP.textContent = isActive ? '📷 FOOTPRINT ON' : '📷 FOOTPRINT OFF';
      if (isActive) {{ popupFP.classList.add('active'); }} else {{ popupFP.classList.remove('active'); }}

      // Position near the click, but clamp inside viewport
      let px = screenX + 14;
      let py = screenY - 60;
      const popW = 200, popH = 170;
      if (px + popW > window.innerWidth) px = screenX - popW - 10;
      if (py < 10) py = 10;
      if (py + popH > window.innerHeight) py = window.innerHeight - popH - 10;

      popup.style.left = px + 'px';
      popup.style.top = py + 'px';
      popup.style.display = 'block';
    }}

    function hideDronePopup() {{
      popup.style.display = 'none';
      currentPopupTarget = null;
    }}

    popupTakeoff.addEventListener('click', function() {{
      if (currentPopupTarget && window.bridge) {{
        window.bridge.on_takeoff_request(currentPopupTarget);
      }}
      hideDronePopup();
    }});
    popupAuto.addEventListener('click', function() {{
      if (currentPopupTarget && window.bridge) {{
        window.bridge.on_start_mission_request(currentPopupTarget);
      }}
      hideDronePopup();
    }});
    popupFP.addEventListener('click', function() {{
      if (currentPopupTarget && window.bridge) {{
        const isActive = fpActiveState[currentPopupTarget] || false;
        fpActiveState[currentPopupTarget] = !isActive;
        window.bridge.on_footprint_toggle(currentPopupTarget);
        // Update button immediately
        popupFP.textContent = !isActive ? '📷 FOOTPRINT ON' : '📷 FOOTPRINT OFF';
        if (!isActive) {{ popupFP.classList.add('active'); }} else {{ popupFP.classList.remove('active'); }}
      }}
    }});

    // Handle clicks on drones — show popup, or hide if clicking elsewhere
    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction(function(click) {{
      const pickedObject = viewer.scene.pick(click.position);
      if (Cesium.defined(pickedObject) && Cesium.defined(pickedObject.id)) {{
        const entityId = pickedObject.id.id;
        if (entityId && entityId.startsWith('drone_')) {{
          const parts = entityId.substring(6).split('_');
          if (parts.length === 2) {{
             const targetId = parts[0] + ':' + parts[1];
             const label = pickedObject.id.name || ('DRONE ' + targetId);
             showDronePopup(targetId, label, click.position.x, click.position.y);
             return;  // Don't hide
          }}
        }}
      }}
      // Clicked elsewhere — hide popup
      hideDronePopup();
    }}, Cesium.ScreenSpaceEventType.LEFT_CLICK);

    // ── Footprints & Video Overlay ───────────────────────────────
    window.updateFootprint = function(id, corners) {{
      if (!corners || corners.length < 3) {{
        window.clearFootprint(id);
        return;
      }}
      const positions = corners.map(c => Cesium.Cartesian3.fromDegrees(c[1], c[0]));
      
      if (!footprintPolygons[id]) {{
        // Create TWO offscreen canvases for double-buffering
        videoCanvases[id] = [document.createElement('canvas'), document.createElement('canvas')];
        activeCanvasIdx[id] = 0;
        
        for (let i = 0; i < 2; i++) {{
            videoCanvases[id][i].width = 640; videoCanvases[id][i].height = 480;
            const ctx = videoCanvases[id][i].getContext('2d');
            ctx.fillStyle = 'rgba(20, 20, 20, 0.1)'; // Neutral dark placeholder
            ctx.fillRect(0, 0, 640, 480);
        }}

        const mat = new Cesium.ImageMaterialProperty({{
          // CallbackProperty evaluates every frame. When activeCanvasIdx swaps, 
          // Cesium detects a new canvas reference and smoothly re-uploads the texture.
          image: new Cesium.CallbackProperty(() => videoCanvases[id][activeCanvasIdx[id]], false),
          transparent: true,
          color: new Cesium.Color(1.0, 1.0, 1.0, 0.95)
        }});
        footprintMaterials[id] = mat;
        
        footprintPolygons[id] = viewer.entities.add({{
          id: 'footprint_' + id,
          polygon: {{
            hierarchy: new Cesium.PolygonHierarchy(positions),
            material: mat,
            classificationType: Cesium.ClassificationType.TERRAIN // Drape over 3D hills
          }}
        }});
      }} else {{
        footprintPolygons[id].polygon.hierarchy = new Cesium.PolygonHierarchy(positions);
      }}
    }};

    window.clearFootprint = function(id) {{
      if (footprintPolygons[id]) {{
        viewer.entities.remove(footprintPolygons[id]);
        delete footprintPolygons[id];
        delete footprintMaterials[id];
        delete videoCanvases[id];
      }}
    }};

    // Use a small pool of images to handle high-frequency updates without blocking
    const imgPool = [new Image(), new Image()];
    const imgBusy = [false, false];
    let frameCount = 0;
    
    function setupImg(idx) {{
        imgPool[idx].onload = function() {{
            for (const id in videoCanvases) {{
                if (!videoCanvases[id]) continue;
                
                // Draw to the INACTIVE canvas (back buffer)
                const nextIdx = activeCanvasIdx[id] === 0 ? 1 : 0;
                const canvas = videoCanvases[id][nextIdx];
                const ctx = canvas.getContext('2d');
                ctx.drawImage(imgPool[idx], 0, 0, canvas.width, canvas.height);
                
                // Swap the active index. The CallbackProperty will return the new canvas 
                // on the next render frame, forcing a smooth texture update.
                activeCanvasIdx[id] = nextIdx;
            }}
            imgBusy[idx] = false;
        }};
        imgPool[idx].onerror = function() {{
            console.error("[Cesium] Image load error in pool " + idx);
            imgBusy[idx] = false;
        }};
    }}
    setupImg(0); setupImg(1);

    window.updateFootprintVideo = function(base64_jpeg) {{
        frameCount++;
        if (frameCount % 30 === 0) console.log("[Cesium] Received " + frameCount + " video frames");

        // Try to find a free image object in the pool
        let selected = -1;
        if (!imgBusy[0]) selected = 0;
        else if (!imgBusy[1]) selected = 1;
        
        if (selected === -1) {{
            // Watchdog: If stuck for more than 500ms, force reset
            if (window._lastFrameTime && Date.now() - window._lastFrameTime > 500) {{
                console.warn("[Cesium] Resetting busy image pool watchdog");
                imgBusy[0] = false; imgBusy[1] = false;
            }}
            return;
        }}
        
        window._lastFrameTime = Date.now();
        imgBusy[selected] = true;
        imgPool[selected].src = 'data:image/jpeg;base64,' + base64_jpeg;
    }};

    // ── Update / create a drone marker ───────────────────────────────
    window.updateDrone = function(id, lat, lon, alt_agl, heading, color, label) {{
      const pos = Cesium.Cartesian3.fromDegrees(lon, lat, alt_agl);
      const col = Cesium.Color.fromCssColorString(color);

      if (drones[id]) {{
        drones[id].position  = pos;
        drones[id].point.color = col;
        if (drones[id].polyline) {{
          drones[id].polyline.positions =
            [pos, Cesium.Cartesian3.fromDegrees(lon, lat, 0)];
        }}
      }} else {{
        drones[id] = viewer.entities.add({{
          id:       'drone_' + id,
          name:     label,
          position: pos,
          point: {{
            pixelSize:  14,
            color:      col,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          }},
          label: {{
            text:           label,
            font:           'bold 11px monospace',
            fillColor:      col,
            outlineColor:   Cesium.Color.BLACK,
            outlineWidth:   2,
            style:          Cesium.LabelStyle.FILL_AND_OUTLINE,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            pixelOffset:    new Cesium.Cartesian2(0, -18),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          }},
          polyline: {{
            positions: [pos, Cesium.Cartesian3.fromDegrees(lon, lat, 0)],
            width: 1,
            material: new Cesium.PolylineDashMaterialProperty({{
              color:      col.withAlpha(0.4),
              dashLength: 12,
            }}),
          }},
        }});
        droneCount++;
        document.getElementById('droneCount').textContent = droneCount;
        if (droneCount === 1) {{
          viewer.camera.flyTo({{
            destination: Cesium.Cartesian3.fromDegrees(lon, lat, 800),
            orientation: {{ heading: Cesium.Math.toRadians(heading), pitch: -0.4, roll: 0 }},
            duration: 3,
          }});
        }}
      }}
    }};

    window.flyTo = function(lat, lon, alt) {{
      viewer.camera.flyTo({{
        destination: Cesium.Cartesian3.fromDegrees(lon, lat, alt),
        duration: 2,
      }});
    }};

    window.addTargetMarker = function(lat, lon, label) {{
      function buildCrosshair() {{
        const c = document.createElement('canvas');
        c.width = c.height = 28;
        const ctx = c.getContext('2d');
        ctx.strokeStyle = '#ff3232';
        ctx.lineWidth   = 2.5;
        ctx.shadowColor = '#ff3232';
        ctx.shadowBlur  = 6;
        ctx.beginPath(); ctx.arc(14, 14, 9, 0, Math.PI*2); ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(14,4);ctx.lineTo(14,24);
        ctx.moveTo(4,14);ctx.lineTo(24,14);
        ctx.stroke();
        return c.toDataURL();
      }}
      const entity = viewer.entities.add({{
        position: Cesium.Cartesian3.fromDegrees(lon, lat, 0),
        billboard: {{
          image:           buildCrosshair(),
          verticalOrigin:  Cesium.VerticalOrigin.BOTTOM,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          scale: 1.5,
        }},
        label: {{
          text:           label,
          font:           'bold 10px monospace',
          fillColor:      Cesium.Color.fromCssColorString('#ff3232'),
          outlineColor:   Cesium.Color.BLACK,
          outlineWidth:   2,
          style:          Cesium.LabelStyle.FILL_AND_OUTLINE,
          verticalOrigin: Cesium.VerticalOrigin.TOP,
          pixelOffset:    new Cesium.Cartesian2(0, 8),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        }},
      }});
      aiTargets.push(entity);
      viewer.camera.flyTo({{
        destination: Cesium.Cartesian3.fromDegrees(lon, lat, 500),
        duration: 2,
      }});
    }};

    window.clearAITargetMarkers = function() {{
      aiTargets.forEach(e => viewer.entities.remove(e));
      aiTargets.length = 0;
    }};

    console.log('[TrueGCS] Cesium 3D viewer ready.');

  }} catch(err) {{
    console.error('[TrueGCS] Cesium init failed:', err);
    document.body.innerHTML =
      '<div style="color:#ff5050;padding:30px;font-family:monospace;background:#090e11;height:100%">'
      + '<b style=\\'font-size:16px\\'>⚠ Cesium Error</b><br><br>' + err.message + '</div>';
  }}
}})();
</script>
</body>
</html>"""
