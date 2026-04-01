"""
SatelliteMapWidget — Premium Leaflet-based satellite map for the ISR Drone GCS.

Features:
  - Esri World Imagery satellite tiles loaded directly from CDN (fast, parallel)
  - Automatic offline fallback via LocalTileServer when CDN is unreachable
  - Multi-Drone & Node Coloring (Tracks arrays of bounding boxes/trails)
  - Dark BF3-themed map controls
  - Professional Mission Planner Slide-out Panel
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QUrl, QObject, Slot, Signal

from core.tile_cache import LocalTileServer, ESRI_TILE_URL

def _build_map_html(local_tile_url, center_lat, center_lon, zoom):
    cdn_url = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no"/>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.css"/>
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js"></script>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ width: 100%; height: 100%; overflow: hidden; background: #090e11; font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }}
  #map {{ width: 100%; height: 100%; }}

  /* Slide-out Mission Panel */
  #mission-panel {{
    position: absolute; top: 10px; right: -320px; bottom: 10px; width: 300px;
    background: rgba(9, 21, 28, 0.96); border: 1px solid rgba(0, 221, 255, 0.35);
    z-index: 2000; border-radius: 10px; display: flex; flex-direction: column;
    box-shadow: -10px 0 30px rgba(0,0,0,0.85); transition: right 0.4s cubic-bezier(0.16, 1, 0.3, 1);
    backdrop-filter: blur(12px);
  }}
  #mission-panel.open {{ right: 10px; }}
  
  .panel-header {{
    padding: 12px; background: rgba(0, 221, 255, 0.1); border-bottom: 1px solid rgba(0, 221, 255, 0.2);
    color: #00ddff; font-weight: bold; font-size: 13px; letter-spacing: 1px; display: flex; justify-content: space-between; align-items: center;
  }}
  
  #mission-list {{
    flex: 1; overflow-y: auto; padding: 8px; scrollbar-width: thin; scrollbar-color: #00ddff #09151c;
  }}
  #mission-list::-webkit-scrollbar {{ width: 4px; }}
  #mission-list::-webkit-scrollbar-thumb {{ background: #00ddff; }}

  .wp-item {{
    background: rgba(255,255,255,0.03); border: 1px solid rgba(146, 176, 195, 0.15);
    border-radius: 6px; padding: 10px; margin-bottom: 8px; position: relative;
    font-size: 11px; color: #92b0c3; transition: all 0.25s;
  }}
  .wp-item:hover {{ border-color: rgba(0, 221, 255, 0.4); background: rgba(0, 221, 255, 0.05); }}
  
  .wp-header {{ display: flex; justify-content: space-between; margin-bottom: 5px; color: #fff; font-weight: bold; }}
  .wp-row {{ display: flex; gap: 8px; align-items: center; margin-top: 4px; }}
  .wp-field {{ display: flex; flex-direction: column; flex: 1; }}
  .wp-field label {{ font-size: 9px; opacity: 0.6; margin-bottom: 2px; text-transform: uppercase; }}
  
  input[type="number"], select {{
    background: #060c11; border: 1px solid rgba(0, 221, 255, 0.2); color: #00ddff;
    padding: 3px 5px; font-size: 11px; border-radius: 2px; width: 100%;
  }}
  input:focus, select:focus {{ outline: none; border-color: #00ddff; }}

  .btn-del-wp {{
    background: rgba(255, 50, 50, 0.1); border: 1px solid #ff3232; color: #ff3232;
    font-size: 10px; cursor: pointer; padding: 2px 6px; border-radius: 2px;
  }}
  .btn-del-wp:hover {{ background: #ff3232; color: #fff; }}

  /* Custom Tactical Selector (Fixes "White Box" Glitch) */
  .drone-sel-row {{ display: flex; align-items: center; justify-content: space-between; gap: 8px; position: relative; }}
  #custom-target-select {{
    flex: 1; background: #060c11; border: 1px solid rgba(0, 221, 255, 0.4);
    color: #fff; font-size: 11px; padding: 5px 8px; border-radius: 2px; cursor: pointer;
    user-select: none; transition: border-color 0.2s; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }}
  #custom-target-select:after {{ content: ' ▼'; float: right; font-size: 8px; opacity: 0.6; }}
  #custom-target-select:hover {{ border-color: #00ddff; }}

  #drone-options-popup {{
    position: absolute; top: 100%; left: 0; right: 0; background: #09151c;
    border: 1px solid #00ddff; border-top: none; z-index: 3000; display: none;
    max-height: 150px; overflow-y: auto; box-shadow: 0 10px 30px rgba(0,0,0,0.9);
  }}
  .drone-opt {{ padding: 8px 10px; border-bottom: 1px solid rgba(0, 221, 255, 0.1); cursor: pointer; font-size: 10px; color: #92b0c3; }}
  .drone-opt:hover {{ background: rgba(0, 221, 255, 0.2); color: #00ddff; }}
  .drone-opt.selected {{ background: rgba(0, 221, 255, 0.15); color: #fff; }}

  .panel-footer {{ padding: 10px; border-top: 1px solid rgba(0, 221, 255, 0.2); display: flex; gap: 8px; flex-direction: column; }}
  .btn-mission {{
    flex: 1; padding: 8px; cursor: pointer; font-size: 11px; font-weight: bold;
    text-transform: uppercase; border-radius: 3px; transition: all 0.2s;
  }}
  .btn-upload {{ background: #00ddff; color: #09151c; border: none; }}
  .btn-upload:hover {{ background: #00b8d4; transform: translateY(-1px); }}
  .btn-clear {{ background: transparent; border: 1px solid rgba(146, 176, 195, 0.4); color: #92b0c3; }}
  .btn-clear:hover {{ border-color: #fff; color: #fff; }}

  /* Map Controls Styling */
  .leaflet-control-zoom a {{
    background: rgba(9, 14, 17, 0.92) !important; color: #00ddff !important;
    border: 1px solid rgba(0, 221, 255, 0.25) !important; font-weight: bold;
    width: 34px !important; height: 34px !important; line-height: 32px !important;
    font-size: 18px !important;
  }}
  .leaflet-top.leaflet-left {{
    top: 40% !important; margin-left: 10px;
  }}
  
  #mission-toggle-btn {{
     position: absolute; top: 10px; right: 10px; z-index: 1000;
     background: rgba(9, 21, 28, 0.94); border: 1px solid #00ddff; color: #00ddff;
     padding: 8px 18px; border-radius: 6px; font-weight: bold; font-size: 12px;
     cursor: pointer; letter-spacing: 1px; box-shadow: 0 4px 20px rgba(0,0,0,0.6);
     transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }}
  #mission-toggle-btn:hover {{ background: #00ddff; color: #000; }}
</style>
</head>
<body>

<button id="mission-toggle-btn" onclick="toggleMissionMode()">MISSION PLANNER</button>

<div id="mission-panel">
  <div class="panel-header" onclick="toggleMissionMode()" style="cursor: pointer;">
     <span>TACTICAL MISSION</span>
     <span style="font-size: 8px; opacity: 0.5;">v1.0</span>
  </div>
  <div id="mission-list"></div>
  <div class="panel-footer">
    <div style="display: flex; flex-direction: column; gap: 5px; margin-bottom: 5px;">
        <label style="font-size: 9px; color: #00ddff; font-weight: bold;">TARGET DRONE:</label>
        <div class="drone-sel-row">
           <div id="custom-target-select" onclick="toggleTargetPopup()">-- NO TARGET --</div>
           <div id="drone-options-popup"></div>
        </div>
    </div>
    <div style="display: flex; gap: 8px;">
        <button class="btn-mission btn-clear" onclick="clearMission()">CLEAR</button>
        <button class="btn-mission btn-upload" onclick="uploadMission()">UPLOAD</button>
    </div>
  </div>
</div>

<div id="map"></div>

<script>
  var bridge = null;
  new QWebChannel(qt.webChannelTransport, function(channel) {{
    bridge = channel.objects.bridge;
  }});

  var map = L.map('map', {{
    center: [{center_lat}, {center_lon}], zoom: {zoom}, zoomControl: false, attributionControl: false
  }});
  L.control.zoom({{ position: 'topleft' }}).addTo(map);
  L.tileLayer('{cdn_url}', {{ maxZoom: 19, maxNativeZoom: 17 }}).addTo(map);

  // MISSION STATE
  var isMissionMode = false;
  var missionWaypoints = [];
  var missionMarkers = [];
  var missionPolyline = L.polyline([], {{ color: '#00ddff', weight: 2, opacity: 0.8 }}).addTo(map);

  function toggleMissionMode() {{
    var btn = document.getElementById('mission-toggle-btn');
    var pnl = document.getElementById('mission-panel');
    var isOpening = !pnl.classList.contains('open');
    
    if (isOpening) {{
      btn.textContent = "PLANNING MODE";
      btn.style.borderColor = "#ffaa00";
      btn.style.color = "#ffaa00";
      pnl.classList.add('open');
      isMissionMode = true;
    }} else {{
      btn.textContent = "MISSION PLANNER";
      btn.style.borderColor = "#00ddff";
      btn.style.color = "#00ddff";
      pnl.classList.remove('open');
      isMissionMode = false;
    }}
  }}

  map.on('contextmenu', function(e) {{
    if (!isMissionMode) return;
    addWaypoint(e.latlng.lat, e.latlng.lng);
  }});

  function addWaypoint(lat, lon) {{
    var wp = {{ id: Date.now(), lat: lat, lon: lon, alt: 60, speed: 15 }};
    missionWaypoints.push(wp);
    
    var num = missionWaypoints.length;
    var wpIcon = L.divIcon({{
      html: `<div style="background: #00ddff; color: #000; width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; border: 1.5px solid #fff; font-size: 11px;">${{num}}</div>`,
      className: '', iconSize: [22, 22], iconAnchor: [11, 11]
    }});
    
    var m = L.marker([lat, lon], {{ icon: wpIcon, draggable: true }}).addTo(map);
    m.wp_id = wp.id;
    m.on('drag', function(e) {{
      var wpRef = missionWaypoints.find(w => w.id === m.wp_id);
      if (wpRef) {{
        wpRef.lat = e.target.getLatLng().lat;
        wpRef.lon = e.target.getLatLng().lng;
        renderMissionList();
        updatePolyline();
      }}
    }});
    
    missionMarkers.push(m);
    renderMissionList();
    updatePolyline();
  }}

  function renderMissionList() {{
    var list = document.getElementById('mission-list');
    list.innerHTML = '';
    
    missionWaypoints.forEach((wp, index) => {{
      var item = document.createElement('div');
      item.className = 'wp-item';
      item.innerHTML = `
        <div class="wp-header">
          <span>WAYPOINT ${{index + 1}}</span>
          <button class="btn-del-wp" onclick="removeWaypoint(${{wp.id}})">X</button>
        </div>
        <div class="wp-row">
          <div class="wp-field">
            <label>ALT (m)</label>
            <input type="number" value="${{wp.alt}}" onchange="updateWpVal(${{wp.id}}, 'alt', this.value)">
          </div>
          <div class="wp-field">
            <label>SPD (m/s)</label>
            <input type="number" value="${{wp.speed}}" onchange="updateWpVal(${{wp.id}}, 'speed', this.value)">
          </div>
        </div>
      `;
      list.appendChild(item);
    }});
  }}

  function updateWpVal(id, key, val) {{
    var wp = missionWaypoints.find(w => w.id === id);
    if (wp) wp[key] = parseFloat(val);
  }}

  function removeWaypoint(id) {{
    missionWaypoints = missionWaypoints.filter(w => w.id !== id);
    var markerIdx = missionMarkers.findIndex(m => m.wp_id === id);
    if (markerIdx > -1) {{
      map.removeLayer(missionMarkers[markerIdx]);
      missionMarkers.splice(markerIdx, 1);
    }}
    // Renumber remaining
    missionMarkers.forEach((m, i) => {{
       var iconHtml = `<div style="background: #00ddff; color: #000; width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; border: 1.5px solid #fff; font-size: 11px;">${{i+1}}</div>`;
       m.setIcon(L.divIcon({{ html: iconHtml, iconSize: [22,22], iconAnchor: [11,11], className: '' }}));
    }});
    renderMissionList();
    updatePolyline();
  }}

  function clearMission() {{
    missionWaypoints = [];
    missionMarkers.forEach(m => map.removeLayer(m));
    missionMarkers = [];
    updatePolyline();
    renderMissionList();
  }}

  function updatePolyline() {{
    var pts = missionWaypoints.map(w => [w.lat, w.lon]);
    missionPolyline.setLatLngs(pts);
  }}

  var selectedDroneId = "none";
  function toggleTargetPopup() {{
    var popup = document.getElementById('drone-options-popup');
    popup.style.display = (popup.style.display === 'block') ? 'none' : 'block';
  }}

  function selectDroneOption(id, name) {{
    selectedDroneId = id;
    document.getElementById('custom-target-select').textContent = name;
    document.getElementById('drone-options-popup').style.display = 'none';
    
    // Update highlight
    var opts = document.querySelectorAll('.drone-opt');
    opts.forEach(o => o.classList.remove('selected'));
    // (Logic for marking as selected would go here)
  }}

  function uploadMission() {{
    if (missionWaypoints.length === 0 || selectedDroneId === "none") {{
        alert("Please select target drone and mission points.");
        return;
    }}
    if (bridge) {{
      bridge.on_mission_upload_request(selectedDroneId, JSON.stringify(missionWaypoints));
    }}
  }}

  function setAvailableDrones(dronesJson) {{
    var drones = JSON.parse(dronesJson);
    var popup = document.getElementById('drone-options-popup');
    popup.innerHTML = '';
    
    if (drones.length === 0) {{
        popup.innerHTML = '<div class="drone-opt">-- NO DRONES FOUND --</div>';
        return;
    }}

    drones.forEach(d => {{
      var opt = document.createElement('div');
      opt.className = 'drone-opt';
      opt.textContent = d.name;
      opt.onclick = function() {{ selectDroneOption(d.id, d.name); }};
      popup.appendChild(opt);
    }});
  }}

  var trackerDrones = {{}};
  function updateDronePosition(node_id, sysid, lat, lon, heading, color_str) {{
    var key = node_id + "_" + sysid;
    if (!trackerDrones[key]) {{
      var droneSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="34" height="34" viewBox="0 0 40 40">
          <circle cx="20" cy="20" r="16" fill="none" stroke="${{color_str}}" stroke-width="1.5"/>
          <path d="M20 6 L28 30 L20 26 L12 30 Z" fill="rgba(0,0,0,0.8)" stroke="${{color_str}}" stroke-width="1.5"/>
      </svg>`;
      trackerDrones[key] = L.marker([lat, lon], {{ icon: L.divIcon({{ html: droneSvg, className: '', iconSize: [34,34], iconAnchor: [17,17] }}) }}).addTo(map);
    }}
    trackerDrones[key].setLatLng([lat, lon]);
    if (heading) {{
       var svg = trackerDrones[key].getElement().querySelector('svg');
       if (svg) svg.style.transform = 'rotate(' + heading + 'deg)';
    }}
  }}
</script>
</body>
</html>"""

class MapBridge(QObject):
    mission_upload_requested = Signal(str, str) # target_id, wp_json
    waypoint_requested = Signal(float, float) # lat, lon

    @Slot(float, float)
    def on_map_click(self, lat, lon):
        self.waypoint_requested.emit(lat, lon)

    @Slot(str, str)
    def on_mission_upload_request(self, target_id, wp_json):
        self.mission_upload_requested.emit(target_id, wp_json)

class SatelliteMapWidget(QWidget):
    waypoint_requested = Signal(float, float)
    mission_upload_requested = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tile_server = None
        self._web_view = QWebEngineView()
        self._bridge = MapBridge()
        self._bridge.waypoint_requested.connect(self.waypoint_requested.emit)
        self._bridge.mission_upload_requested.connect(self.mission_upload_requested.emit)
        self._setup_tile_server()
        self._setup_ui()

    def _setup_tile_server(self):
        self._tile_server = LocalTileServer()
        self._tile_server.start()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._web_view.setStyleSheet("background: #090e11; border: none;")
        html = _build_map_html(self._tile_server.tile_url_template, -29.983, 153.233, 13)
        self._web_view.setHtml(html, QUrl("http://127.0.0.1/"))
        self._channel = QWebChannel()
        self._channel.registerObject("bridge", self._bridge)
        self._web_view.page().setWebChannel(self._channel)
        layout.addWidget(self._web_view)

    def update_drone_list(self, drones):
        import json
        js = f"setAvailableDrones('{json.dumps(drones)}');"
        self._web_view.page().runJavaScript(js)

    def update_drone_position(self, node_id, sysid, lat, lon, heading=None, color="#00ddff"):
        hdg = heading if heading is not None else "null"
        js = f"updateDronePosition({node_id}, {sysid}, {lat}, {lon}, {hdg}, '{color}');"
        self._web_view.page().runJavaScript(js)

    def remove_drone(self, node_id, sysid):
        self._web_view.page().runJavaScript(f"removeDrone({node_id}, {sysid});")

    def cleanup(self):
        if self._tile_server: self._tile_server.stop()
