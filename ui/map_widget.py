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
    z-index: 6000; border-radius: 10px; display: flex; flex-direction: column;
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
  
  .btn-takeoff {{ background: #ffaa00; color: #000; border: none; margin-bottom: 5px; }}
  .btn-takeoff:hover {{ background: #e69900; transform: translateY(-1px); }}
  
  .btn-start {{ background: #00ff00; color: #000; border: none; }}
  .btn-start:hover {{ background: #00cc00; transform: translateY(-1px); }}

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
      position: absolute; top: 10px; right: 10px; z-index: 5000;
      background: rgba(9, 21, 28, 0.94); border: 1px solid #00ddff; color: #00ddff;
      padding: 8px 18px; border-radius: 6px; font-weight: bold; font-size: 12px;
      cursor: pointer; letter-spacing: 1px; box-shadow: 0 4px 20px rgba(0,0,0,0.6);
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
   }}
  #mission-toggle-btn:hover {{ background: #00ddff; color: #000; }}
  
  /* Custom Popup Styling */
  .gcs-popup .leaflet-popup-content-wrapper {{ background: rgba(9, 21, 28, 0.94); border: 1px solid #00ddff; border-radius: 4px; padding: 0; box-shadow: 0 4px 15px rgba(0,0,0,0.8); }}
  .gcs-popup .leaflet-popup-tip {{ background: #00ddff; }}
  .gcs-popup .leaflet-popup-content {{ margin: 8px; width: auto !important; }}

  /* Camera Footprint Overlay Styling */
  #footprint-toggle-btn {{
      position: absolute; top: 10px; left: 50%; transform: translateX(-50%); z-index: 5000;
      background: rgba(9, 21, 28, 0.94); border: 1px solid #ffaa00; color: #ffaa00;
      padding: 6px 14px; border-radius: 6px; font-weight: bold; font-size: 11px;
      cursor: pointer; letter-spacing: 0.5px; box-shadow: 0 4px 20px rgba(0,0,0,0.6);
      display: none; transition: all 0.3s;
   }}
  #footprint-toggle-btn:hover {{ background: rgba(255, 170, 0, 0.2); }}
  #footprint-toggle-btn.active {{ background: #ffaa00; color: #000; }}

  /* Footprint info label */
  #footprint-info {{
      position: absolute; bottom: 10px; left: 10px; z-index: 5000;
      background: rgba(9, 21, 28, 0.9); border: 1px solid rgba(255, 170, 0, 0.4);
      color: #ffaa00; padding: 6px 12px; border-radius: 4px; font-size: 10px;
      font-family: monospace; display: none; pointer-events: none;
  }}
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
        <label style="font-size: 9px; color: #00ddff; font-weight: bold; opacity: 0.8;">SELECTED TARGET:</label>
        <div id="custom-target-display" style="color: #fff; font-size: 11px; padding: 5px 0; font-weight: bold;">-- NO TARGET --</div>
    </div>
    <div style="display: flex; gap: 8px; margin-bottom: 8px;">
        <button class="btn-mission btn-clear" onclick="clearMission()">CLEAR</button>
        <button class="btn-mission btn-upload" onclick="uploadMission()">UPLOAD</button>
    </div>
    <div style="display: flex; flex-direction: column; gap: 6px;">
        <button class="btn-mission btn-takeoff" onclick="takeoff()">TAKEOFF (50m)</button>
        <button class="btn-mission btn-start" onclick="startMission()">START MISSION (AUTO)</button>
    </div>
  </div>
</div>

<div id="map"></div>

<button id="footprint-toggle-btn" onclick="toggleFootprints()">FOOTPRINT</button>
<div id="footprint-info"></div>

<script>
  var bridge = null;
  new QWebChannel(qt.webChannelTransport, function(channel) {{
    bridge = channel.objects.bridge;
  }});

  var map = L.map('map', {{
    center: [{center_lat}, {center_lon}], zoom: {zoom}, zoomControl: false, attributionControl: false
  }});
  L.control.zoom({{ position: 'topleft' }}).addTo(map);
  L.tileLayer('{cdn_url}', {{ maxZoom: 20, maxNativeZoom: 19 }}).addTo(map);

  // MISSION STATE
  var isMissionMode = false;
  var missionWaypoints = [];
  var missionMarkers = [];
  var missionPolyline = L.polyline([], {{ color: '#00ddff', weight: 2, opacity: 0.8 }}).addTo(map);

  // =========================================================================
  // CAMERA FOOTPRINT OVERLAY SYSTEM
  // =========================================================================
  var footprintsVisible = false;
  var footprintLayers = {{}};  // key -> L.polygon reference (outline)
  var activeFootprints = {{}};  // key -> true/false per-drone state
  var footprintVideoElements = {{}};  // key -> {{overlay, video}} for video streaming
  var footprintFrameQueue = {{}}; // key -> array of jpeg bytes to display

  function setDroneFootprintState(key, isActive) {{
    // key is "node_id:sysid" from Python, convert to "_" separator for internal use
    var internalKey = key.replace(":", "_");
    activeFootprints[internalKey] = isActive;
    console.log("[JS] setDroneFootprintState: key=" + key + " internalKey=" + internalKey + " isActive=" + isActive);
    console.log("[JS] Available footprintLayers keys:", Object.keys(footprintLayers));
    if (isActive) {{
      // Trigger recalculation via footprint manager signal
      console.log("[JS] Footprint enabled for " + key);
    }} else {{
      // Clear the polygon and video overlay using internalKey
      if (footprintLayers[internalKey]) {{
        console.log("[JS] Clearing footprint layer for internalKey=" + internalKey);
        map.removeLayer(footprintLayers[internalKey]);
        delete footprintLayers[internalKey];
      }} else {{
        console.log("[JS] No footprint layer found for internalKey=" + internalKey);
      }}
      // Remove video overlay if exists (using div-based approach)
      clearFootprintVideoFromKey(internalKey);
      delete footprintFrameQueue[internalKey];
      console.log("[JS] Footprint disabled for " + key);
    }}
  }}
  
  // Helper to clear video overlay by internalKey (underscore format)
  function clearFootprintVideoFromKey(key) {{
    var vpe = footprintVideoElements[key];
    if (vpe) {{
      // Remove the element from DOM
      if (vpe.element && vpe.element.parentNode) {{
        vpe.element.parentNode.removeChild(vpe.element);
      }}
      footprintVideoElements[key] = null;
      console.log("[JS] Cleared footprint video overlay for key=" + key);
    }}
  }}

  function toggleFootprints() {{
    footprintsVisible = !footprintsVisible;
    var btn = document.getElementById('footprint-toggle-btn');
    var info = document.getElementById('footprint-info');

    if (footprintsVisible) {{
      btn.classList.add('active');
      btn.textContent = "FOOTPRINTS ON";
      info.style.display = 'block';
      // Show existing footprint layers
      for (var key in footprintLayers) {{
        if (footprintLayers[key]) footprintLayers[key].addTo(map);
      }}
    }} else {{
      btn.classList.remove('active');
      btn.textContent = "FOOTPRINT";
      info.style.display = 'none';
      // Hide all footprint layers and video overlays
      for (var key in footprintLayers) {{
        if (footprintLayers[key]) {{
          map.removeLayer(footprintLayers[key]);
          delete footprintLayers[key];
        }}
      }}
      footprintLayers = {{}};
      // Also remove all video overlays
      for (var vk in footprintVideoElements) {{
        clearFootprintVideoFromKey(vk);
      }}
      footprintVideoElements = {{}};
    }}
  }}

  function updateFootprint(node_id, sysid, corners, area_m2) {{
    if (!corners || corners.length < 3) return;
    
    // Check if this specific drone has footprint enabled OR global is on
    var key = node_id + "_" + sysid;
    var droneActive = activeFootprints[key] === true;
    if (!droneActive && !footprintsVisible) return;
    var latLngs = corners.map(function(c) {{ return [c[0], c[1]]; }});

    // Create or update the footprint polygon
    if (footprintLayers[key]) {{
      footprintLayers[key].setLatLngs(latLngs);
    }} else {{
      footprintLayers[key] = L.polygon(latLngs, {{
        color: '#ffaa00',
        weight: 2,
        opacity: 0.9,
        fillColor: '#ffaa00',
        fillOpacity: 0.15,
        dashArray: '4, 4',
        className: 'footprint-polygon'
      }}).addTo(map);

      // Add tooltip with area info
      footprintLayers[key].bindTooltip(
        "Camera Footprint<br>Area: " + Math.round(area_m2) + " m²",
        {{ sticky: true, direction: 'top', className: 'footprint-tooltip' }}
      );
    }}

    // Update info panel
    var info = document.getElementById('footprint-info');
    if (info) {{
      info.innerHTML = "FP: Node " + node_id + ":Sys" + sysid + " | Area: " + Math.round(area_m2) + " m²";
    }}
  }}

  function clearFootprint(node_id, sysid) {{
    var key = node_id + "_" + sysid;
    if (footprintLayers[key]) {{
      map.removeLayer(footprintLayers[key]);
      delete footprintLayers[key];
    }}
    // Also clear video overlay
    clearFootprintVideoFromKey(key);
  }}

  function clearAllFootprints() {{
    for (var key in footprintLayers) {{
      if (footprintLayers[key]) {{
        map.removeLayer(footprintLayers[key]);
      }}
    }}
    footprintLayers = {{}};
    // Clear all video overlays too
    for (var vk in footprintVideoElements) {{
      clearFootprintVideoFromKey(vk);
    }}
    footprintVideoElements = {{}};
  }}

  // =========================================================================
  // VIDEO FRAME UPDATE FOR FOOTPRINT OVERLAY
  // =========================================================================
  
  /**
   * Create a video overlay element for footprint display.
   * Uses Leaflet's overlay pane for proper z-index management.
   */
  function createFootprintVideoOverlay(node_id, sysid) {{
    var key = node_id + "_" + sysid;
    
    // Check if this drone has footprint enabled
    var droneActive = activeFootprints[key] === true;
    if (!droneActive) {{
      console.warn("[JS] Footprint video skipped: drone not active for key=" + key);
      return null;
    }}
    
    // Don't create if already exists
    if (footprintVideoElements[key]) {{
      console.log("[JS] Footprint video overlay already exists for key=" + key);
      return footprintVideoElements[key];
    }}
    
    console.log("[JS] Creating footprint video overlay for key=" + key);
    
    // Create a unique ID for this overlay's container div
    var containerId = 'fp-video-' + key.replace(/_/g, '-');
    
    // Create the outer container with styling
    var overlayDiv = document.createElement('div');
    overlayDiv.id = containerId;
    overlayDiv.style.width = '180px';
    overlayDiv.style.height = '135px';
    overlayDiv.style.position = 'absolute';  // Position relative to map container
    overlayDiv.style.pointerEvents = 'none';  // Let clicks pass through to map
    overlayDiv.style.border = '2px solid rgba(255, 170, 0, 0.9)';
    overlayDiv.style.borderRadius = '6px';
    overlayDiv.style.overflow = 'hidden';
    overlayDiv.style.background = '#000';
    overlayDiv.style.boxShadow = '0 2px 12px rgba(0,0,0,0.6)';
    overlayDiv.style.opacity = '0.85';
    overlayDiv.style.zIndex = '10000';  // High z-index to be above all Leaflet panes
    
    // Create an img element (not video — we're displaying JPEG stills)
    var imgEl = document.createElement('img');
    imgEl.style.width = '100%';
    imgEl.style.height = '100%';
    imgEl.style.objectFit = 'cover';
    imgEl.style.display = 'block';
    imgEl.style.background = '#000';
    
    overlayDiv.appendChild(imgEl);
    
    // Add directly to the map container (NOT overlay pane) because Leaflet's
    // .leaflet-overlay-pane has transform: translate3d(...) which breaks absolute positioning
    var mapContainer = map.getContainer();
    
    // Ensure the map container has position: relative for absolute children
    if (mapContainer.style.position !== 'relative' && mapContainer.style.position !== 'absolute') {{
      mapContainer.style.position = 'relative';
    }}
    
    console.log("[JS] Appending overlayDiv directly to map container");
    mapContainer.appendChild(overlayDiv);
    
    // Verify the element is in the DOM
    if (!document.body.contains(overlayDiv) && !mapContainer.contains(overlayDiv)) {{
      console.error("[JS] ERROR: overlayDiv was NOT appended to DOM!");
    }} else {{
      console.log("[JS] overlayDiv successfully added to DOM");
    }}
    
    // Store the reference
    var overlayRef = {{
      element: overlayDiv,
      img: imgEl,
      containerId: containerId,
      node_id: node_id,
      sysid: sysid
    }};
    
    footprintVideoElements[key] = overlayRef;
    
    console.log("[JS] Footprint video overlay created and stored for key=" + key);
    
    return overlayRef;
  }}
  
  /**
   * Update the video frame for a footprint overlay.
   */
  function updateFootprintVideo(node_id, sysid, jpeg_base64) {{
    var key = node_id + "_" + sysid;
    
    // Log every call for debugging
    console.log("[JS] updateFootprintVideo called: key=" + key + ", jpeg_base64 length=" + (jpeg_base64 ? jpeg_base64.length : 0));
    
    // Check if drone has footprint enabled
    if (activeFootprints[key] !== true) {{
      console.log("[JS] updateFootprintVideo skipped: drone not active for key=" + key);
      return;
    }}
    
    // Create overlay if it doesn't exist yet
    if (!footprintVideoElements[key]) {{
      console.log("[JS] Creating new footprint video overlay in updateFootprintVideo");
      createFootprintVideoOverlay(node_id, sysid);
    }}
    
    // Update the img source with new frame
    var vpe = footprintVideoElements[key];
    if (vpe && vpe.img) {{
      vpe.img.src = "data:image/jpeg;base64," + jpeg_base64;
    }}
  }}
  
  /**
   * Position the video overlay at a specific lat/lon on the map.
   */
  function updateFootprintVideoPosition(node_id, sysid, lat, lon) {{
    var key = node_id + "_" + sysid;
    var vpe = footprintVideoElements[key];
    
    if (!vpe || !vpe.element) {{
      console.log("[JS] WARNING: No overlay element for key=" + key);
      return;
    }}
    
    // Convert lat/lon to pixel coordinates relative to the map container
    var point = map.latLngToContainerPoint([lat, lon]);
    
    // Position the overlay centered on the point (offset by half its size)
    vpe.element.style.left = (point.x - 90) + 'px';   // 180px / 2 = 90px offset
    vpe.element.style.top = (point.y - 67) + 'px';    // 135px / 2 = 67.5px offset
    
    console.log("[JS] Positioned video overlay for key=" + key + " at pixel(" + point.x + "," + point.y + "), element offsetLeft=" + vpe.element.offsetLeft + " offsetTop=" + vpe.element.offsetTop);
    
    // Debug: log the map container's dimensions and offset
    var mc = map.getContainer();
    console.log("[JS] Map container: width=" + mc.offsetWidth + ", height=" + mc.offsetHeight);
  }}

  function clearFootprintVideo(node_id, sysid) {{
    var key = node_id + "_" + sysid;
    var vpe = footprintVideoElements[key];
    
    if (vpe) {{
      // Remove the element from DOM
      if (vpe.element && vpe.element.parentNode) {{
        vpe.element.parentNode.removeChild(vpe.element);
      }}
      
      // Clear the reference
      footprintVideoElements[key] = null;
      console.log("[JS] Cleared footprint video overlay for key=" + key);
    }}
  }}

  function setFootprintVisibility(visible) {{
    if (visible && !footprintsVisible) {{
      footprintsVisible = true;
      var btn = document.getElementById('footprint-toggle-btn');
      btn.classList.add('active');
      btn.textContent = "FOOTPRINTS ON";
      document.getElementById('footprint-info').style.display = 'block';
      for (var key in footprintLayers) {{
        if (footprintLayers[key]) footprintLayers[key].addTo(map);
      }}
    }} else if (!visible && footprintsVisible) {{
      footprintsVisible = false;
      var btn = document.getElementById('footprint-toggle-btn');
      btn.classList.remove('active');
      btn.textContent = "FOOTPRINT";
      document.getElementById('footprint-info').style.display = 'none';
      for (var key in footprintLayers) {{
        if (footprintLayers[key]) map.removeLayer(footprintLayers[key]);
      }}
    }}
  }}

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

  function takeoff() {{
    if (selectedDroneId === "none") {{
        alert("Please select target drone.");
        return;
    }}
    if (bridge) bridge.on_takeoff_request(selectedDroneId);
  }}

  function startMission() {{
    if (selectedDroneId === "none") {{
        alert("Please select target drone.");
        return;
    }}
    if (bridge) bridge.on_start_mission_request(selectedDroneId);
  }}

  function setActiveDrone(id, name) {{
    selectedDroneId = id;
    var display = document.getElementById('custom-target-display');
    if (display) display.textContent = name;
    console.log("Map: Active Target Synced -> " + name + " (" + id + ")");
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
      
      var popupContent = `
        <div style="font-family: monospace; color: #fff; min-width: 150px;">
            <div style="font-weight: bold; color: #00ddff; margin-bottom: 8px; border-bottom: 1px solid rgba(0,221,255,0.3); padding-bottom: 4px;">DRONE ${{sysid}} (Node ${{node_id}})</div>
            <button class="btn-takeoff" onclick="console.log('TAKEOFF clicked'); if(window.bridge) bridge.on_takeoff_request('${{node_id}}:${{sysid}}')" style="width:100%; padding: 8px; cursor: pointer; border-radius: 3px; font-weight: bold;">TAKEOFF</button>
            <button class="btn-start" onclick="console.log('AUTO MODE clicked'); if(window.bridge) bridge.on_start_mission_request('${{node_id}}:${{sysid}}')" style="width:100%; padding: 8px; cursor: pointer; margin-top:4px; border-radius: 3px; font-weight: bold;">AUTO MODE</button>
            <div style="margin-top: 8px; border-top: 1px solid rgba(255,170,0,0.3); padding-top: 6px;">
                <button id="fp-btn-${{node_id}}:${{sysid}}" onclick="console.log('FOOTPRINT toggle clicked for ${{node_id}}:${{sysid}}'); if(window.bridge) bridge.on_footprint_toggle('${{node_id}}:${{sysid}}')" style="width:100%; padding: 8px; cursor: pointer; border-radius: 3px; font-weight: bold; background: rgba(255,170,0,0.2); border: 1px solid #ffaa00; color: #ffaa00;">
                    📷 FOOTPRINT OFF
                </button>
            </div>
        </div>
      `;
      trackerDrones[key].bindPopup(popupContent, {{className: 'gcs-popup', closeButton: false}});
      
      // Context Menu Listener - ATTACH ONCE ONLY 🛰️
      trackerDrones[key].on('contextmenu', function(e) {{
        if (bridge) {{
          bridge.on_drone_context_menu(node_id + ":" + sysid);
        }}
        L.DomEvent.stopPropagation(e);
      }});
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
    takeoff_requested = Signal(str) # target_id
    start_mission_requested = Signal(str) # target_id
    drone_context_menu_requested = Signal(str) # target_id
    footprint_toggle_requested = Signal(str) # target_id
    footprint_state_changed = Signal(str, bool) # target_id, is_active

    @Slot(str)
    def on_drone_context_menu(self, target_id):
        self.drone_context_menu_requested.emit(target_id)

    @Slot(str)
    def on_footprint_toggle(self, target_id):
        self.footprint_toggle_requested.emit(target_id)

    @Slot(str, bool)
    def on_footprint_toggle_js(self, target_id, is_active):
        """Called from JavaScript to update button text."""
        pass  # Handled via Python side

    @Slot(str, bool)
    def set_drone_footprint_state(self, target_id, is_active):
        """Notify JavaScript about per-drone footprint state change."""
        self.footprint_state_changed.emit(target_id, is_active)

    @Slot(float, float)
    def on_map_click(self, lat, lon):
        self.waypoint_requested.emit(lat, lon)

    @Slot(str, str)
    def on_mission_upload_request(self, target_id, wp_json):
        self.mission_upload_requested.emit(target_id, wp_json)

    @Slot(str)
    def on_takeoff_request(self, target_id):
        self.takeoff_requested.emit(target_id)

    @Slot(str)
    def on_start_mission_request(self, target_id):
        self.start_mission_requested.emit(target_id)

class SatelliteMapWidget(QWidget):
    waypoint_requested = Signal(float, float)
    mission_upload_requested = Signal(str, str)
    takeoff_requested = Signal(str)
    start_mission_requested = Signal(str)
    drone_context_menu_requested = Signal(str)
    footprint_toggle_requested = Signal(str)  # target_id
    footprint_state_changed = Signal(str, bool)  # target_id, is_active

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tile_server = None
        self._web_view = QWebEngineView()
        self._bridge = MapBridge()
        self._bridge.waypoint_requested.connect(self.waypoint_requested.emit)
        self._bridge.mission_upload_requested.connect(self.mission_upload_requested.emit)
        self._bridge.takeoff_requested.connect(self.takeoff_requested.emit)
        self._bridge.start_mission_requested.connect(self.start_mission_requested.emit)
        self._bridge.drone_context_menu_requested.connect(self.drone_context_menu_requested.emit)
        self._bridge.footprint_toggle_requested.connect(self.footprint_toggle_requested.emit)
        # Connect footprint state changes to update _active_fp_target tracking
        self._bridge.footprint_state_changed.connect(self._on_footprint_state_changed)
        # Track which drone footprint is active for video overlay routing
        self._active_fp_target = None  # e.g. "1:1" or None
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

    def set_active_drone(self, node_id, sysid, name):
        target_id = f"{node_id}:{sysid}"
        js = f"setActiveDrone('{target_id}', '{name}');"
        self._web_view.page().runJavaScript(js)

    def update_drone_position(self, node_id, sysid, lat, lon, heading=None, color="#00ddff"):
        hdg = heading if heading is not None else "null"
        js = f"updateDronePosition({node_id}, {sysid}, {lat}, {lon}, {hdg}, '{color}');"
        self._web_view.page().runJavaScript(js)
        
        # Update video overlay position if this drone has an active footprint with video
        target_id = f"{node_id}:{sysid}"
        if self._active_fp_target == target_id:
            js = f"updateFootprintVideoPosition({node_id}, {sysid}, {lat}, {lon});"
            self._web_view.page().runJavaScript(js)

    def remove_drone(self, node_id, sysid):
        self._web_view.page().runJavaScript(f"removeDrone({node_id}, {sysid});")

    # ------------------------------------------------------------------
    # Camera Footprint Controls
    # ------------------------------------------------------------------

    def set_footprints_visible(self, visible):
        """Show or hide all footprint overlays on the map."""
        js = f"setFootprintVisibility({str(visible).lower()});"
        self._web_view.page().runJavaScript(js)

    def update_footprint(self, node_id, sysid, corners, area_m2):
        """Update the footprint polygon for a specific drone.

        Parameters:
            node_id: Drone node identifier (int)
            sysid: Drone system ID (int)
            corners: List of [lat, lon] pairs or None
            area_m2: Approximate ground area in square metres (float)
        """
        if corners is None or len(corners) < 3:
            # Clear footprint if invalid
            js = f"updateFootprint({node_id}, {sysid}, null, 0);"
        else:
            # Convert corners to JSON-compatible format
            corners_str = "[" + ",".join(f"[{c[0]},{c[1]}]" for c in corners) + "]"
            js = f"updateFootprint({node_id}, {sysid}, {corners_str}, {area_m2});"
        self._web_view.page().runJavaScript(js)

    def add_footprint(self, node_id, sysid, corners, area_m2):
        """Add/update a camera footprint polygon on the map.

        Parameters:
            node_id: Drone node ID
            sysid: Drone system ID
            corners: List of [lat, lon] pairs forming the footprint polygon
            area_m2: Approximate ground area in square metres
        """
        if not corners or len(corners) < 3:
            return
        corners_str = "[" + ",".join(f"[{c[0]},{c[1]}]" for c in corners) + "]"
        js = f"updateFootprint({node_id}, {sysid}, {corners_str}, {area_m2});"
        self._web_view.page().runJavaScript(js)

    def clear_footprint(self, node_id, sysid):
        """Clear the footprint overlay for a specific drone."""
        js = f"clearFootprint({node_id}, {sysid});"
        self._web_view.page().runJavaScript(js)
        # Also clear video overlay
        js = f"clearFootprintVideo({node_id}, {sysid});"
        self._web_view.page().runJavaScript(js)

    def clear_all_footprints(self):
        """Clear all footprint overlays."""
        self._web_view.page().runJavaScript("clearAllFootprints();")
    def _on_footprint_state_changed(self, target_id, is_active):
        """Called when MapBridge receives footprint state change from JavaScript.
        
        This updates the internal tracking for video overlay routing.
        """
        if is_active:
            self._active_fp_target = target_id
        elif self._active_fp_target == target_id:
            self._active_fp_target = None
    
    def set_drone_footprint_state(self, node_id, sysid, is_active):
        """Notify JavaScript about per-drone footprint state change.
        
        Also tracks the active drone for video overlay routing.
        
        Parameters:
            node_id: Drone node ID
            sysid: Drone system ID
            is_active: True if footprint is active, False otherwise
        """
        target_id = f"{node_id}:{sysid}"
        js = f"setDroneFootprintState('{target_id}', {str(is_active).lower()});"
        self._web_view.page().runJavaScript(js)
        
        
    def update_footprint_video_bytes(self, node_id, jpeg_bytes):
        """Update the video frame for a drone's footprint overlay from raw bytes.
        
        The VideoThread emits with node_id="main", so we use the currently
        active drone footprint target_id instead.
        
        Parameters:
            node_id: Drone node ID (or "main" from VideoThread)
            jpeg_bytes: Raw JPEG image bytes
        """
        # Debug logging
        if not hasattr(self, '_fp_update_count'):
            self._fp_update_count = 0
        self._fp_update_count += 1
        
        # If node_id is "main" (from VideoThread), use the active drone footprint key
        if node_id == "main":
            if not self._active_fp_target:
                # No active footprint, skip but log occasionally
                if self._fp_update_count % 50 == 1:
                    print(f"[Python] update_footprint_video_bytes: skipping, no _active_fp_target")
                return
            target_id = self._active_fp_target
        else:
            target_id = f"{node_id}:1"
        
        # Parse target_id to get node_id and sysid for JS call
        parts = target_id.split(":")
        if len(parts) == 2:
            j_nid, j_sid = parts[0], int(parts[1])
        else:
            # Fallback: use "main" as node_id and sysid=1
            j_nid, j_sid = "main", 1
        
        import base64
        encoded = base64.b64encode(jpeg_bytes).decode('ascii')
        
        # Escape the base64 string for JavaScript safety
        safe_encoded = encoded.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "")
        
        # Log every 100th update to avoid spam
        if self._fp_update_count % 100 == 1:
            print(f"[Python] update_footprint_video_bytes: j_nid={j_nid}, j_sid={j_sid}, jpeg_bytes_len={len(jpeg_bytes)}, _active_fp_target={self._active_fp_target}")
        
        js = f"updateFootprintVideo('{j_nid}', {j_sid}, '{safe_encoded}');"
        self._web_view.page().runJavaScript(js)
        
    def update_footprint_video(self, node_id, sysid, jpeg_base64):
        """Update the video frame for a specific drone's footprint overlay.
        
        Parameters:
            node_id: Drone node ID
            sysid: Drone system ID
            jpeg_base64: Base64-encoded JPEG image data (string)
        """
        js = f"updateFootprintVideo({node_id}, {sysid}, '{jpeg_base64}');"
        self._web_view.page().runJavaScript(js)
        """Clear all footprint overlays."""
        self._web_view.page().runJavaScript("clearAllFootprints();")

    def show_footprint_toggle_button(self, show):
        """Show or hide the footprint toggle button on the map."""
        display = "block" if show else "none"
        js = f"document.getElementById('footprint-toggle-btn').style.display = '{display}';"
        self._web_view.page().runJavaScript(js)

    def cleanup(self):
        if self._tile_server: self._tile_server.stop()
