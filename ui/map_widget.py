"""
SatelliteMapWidget — Premium Leaflet-based satellite map for the ISR Drone GCS.

Features:
  - Esri World Imagery satellite tiles loaded directly from CDN (fast, parallel)
  - Automatic offline fallback via LocalTileServer when CDN is unreachable
  - Live drone marker with heading rotation (SVG aircraft icon)
  - Flight trail polyline
  - Dark BF3-themed map controls
  - Smooth flyTo animations on position updates
  - Coordinate readout overlay
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QUrl, QObject, Slot, Signal

from core.tile_cache import LocalTileServer, ESRI_TILE_URL


# ---------------------------------------------------------------------------
# The Leaflet HTML template — hand-crafted, no folium dependency
# ---------------------------------------------------------------------------

def _build_map_html(local_tile_url, center_lat, center_lon, zoom):
    """Generate the full Leaflet map HTML with BF3 styling."""

    # Esri CDN URL for direct browser loading (fast, parallel HTTP/2)
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
  /* ---- Base Reset ---- */
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ width: 100%; height: 100%; overflow: hidden; background: #090e11; }}
  #map {{ width: 100%; height: 100%; }}

  /* ---- BF3 Dark Theme for Leaflet Controls ---- */
  .leaflet-control-zoom a {{
    background: rgba(9, 14, 17, 0.92) !important;
    color: #00ddff !important;
    border: 1px solid rgba(0, 221, 255, 0.25) !important;
    font-weight: bold;
    width: 32px !important;
    height: 32px !important;
    line-height: 30px !important;
    font-size: 16px !important;
    transition: all 0.2s ease;
  }}
  .leaflet-control-zoom a:hover {{
    background: rgba(0, 221, 255, 0.15) !important;
    border-color: #00ddff !important;
    box-shadow: 0 0 8px rgba(0, 221, 255, 0.3);
  }}
  .leaflet-control-zoom {{
    border: none !important;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.5) !important;
  }}

  .leaflet-control-attribution {{
    background: rgba(9, 14, 17, 0.75) !important;
    color: rgba(146, 176, 195, 0.5) !important;
    font-size: 9px !important;
    border: none !important;
  }}
  .leaflet-control-attribution a {{
    color: rgba(0, 221, 255, 0.5) !important;
  }}

  /* ---- Status indicator ---- */
  #status-indicator {{
    position: absolute;
    bottom: 24px;
    left: 10px;
    z-index: 1000;
    background: rgba(9, 14, 17, 0.85);
    border: 1px solid rgba(0, 221, 255, 0.2);
    border-radius: 3px;
    padding: 4px 10px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 10px;
    color: rgba(146, 176, 195, 0.6);
    pointer-events: none;
    backdrop-filter: blur(4px);
    transition: all 0.3s ease;
  }}
  #status-indicator.online {{ border-color: rgba(0, 255, 120, 0.3); color: rgba(0, 255, 120, 0.7); }}
  #status-indicator.offline {{ border-color: rgba(255, 180, 0, 0.3); color: rgba(255, 180, 0, 0.7); }}



  /* ---- Crosshair Overlay ---- */
  #crosshair {{
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    z-index: 999;
    pointer-events: none;
    width: 30px;
    height: 30px;
    opacity: 0.25;
  }}

  /* ---- Drone marker glow animation ---- */
  @keyframes droneGlow {{
    0%   {{ filter: drop-shadow(0 0 4px rgba(0, 221, 255, 0.6)); }}
    50%  {{ filter: drop-shadow(0 0 10px rgba(0, 221, 255, 0.9)); }}
    100% {{ filter: drop-shadow(0 0 4px rgba(0, 221, 255, 0.6)); }}
  }}
  .drone-icon {{
    animation: droneGlow 2s ease-in-out infinite;
  }}
</style>
</head>
<body>



<!-- Status indicator -->
<div id="status-indicator" class="online">● CDN ONLINE</div>

<!-- Center crosshair -->
<svg id="crosshair" viewBox="0 0 30 30">
  <line x1="15" y1="0" x2="15" y2="12" stroke="#00ddff" stroke-width="1"/>
  <line x1="15" y1="18" x2="15" y2="30" stroke="#00ddff" stroke-width="1"/>
  <line x1="0" y1="15" x2="12" y2="15" stroke="#00ddff" stroke-width="1"/>
  <line x1="18" y1="15" x2="30" y2="15" stroke="#00ddff" stroke-width="1"/>
  <circle cx="15" cy="15" r="2" fill="none" stroke="#00ddff" stroke-width="0.5"/>
</svg>

<div id="map"></div>

<script>
  // ---- QWebChannel Setup ----
  var bridge = null;
  new QWebChannel(qt.webChannelTransport, function(channel) {{
    bridge = channel.objects.bridge;
    console.log("QWebChannel connected");
  }});

  // ---- Initialize Map ----
  var map = L.map('map', {{
    center: [{center_lat}, {center_lon}],
    zoom: {zoom},
    zoomControl: false,
    attributionControl: true,
    preferCanvas: true
  }});

  // Place zoom controls at bottom-right to avoid overlap with Qt GroupBox title
  L.control.zoom({{ position: 'bottomright' }}).addTo(map);

  // ---- Tile Layer: Direct CDN with offline fallback ----
  // Primary: Esri CDN loaded directly by the browser (fast, parallel HTTP/2)
  // Note: Esri tile URL uses /tile/z/y/x format
  var cdnUrl = '{cdn_url}';
  var localUrl = '{local_tile_url}';
  var isOffline = false;
  var failCount = 0;
  var failThreshold = 5;  // Switch to offline mode after 5 consecutive failures

  // Create a custom tile layer with automatic fallback
  var EsriFallbackLayer = L.TileLayer.extend({{
    _currentUrl: cdnUrl,

    getTileUrl: function(coords) {{
      // Esri uses z/y/x, Leaflet provides z/x/y
      if (this._currentUrl === cdnUrl) {{
        return cdnUrl.replace('{{z}}', coords.z).replace('{{y}}', coords.y).replace('{{x}}', coords.x);
      }} else {{
        // Local server uses z/x/y
        return localUrl.replace('{{z}}', coords.z).replace('{{x}}', coords.x).replace('{{y}}', coords.y);
      }}
    }},

    _switchToOffline: function() {{
      if (!isOffline) {{
        isOffline = true;
        this._currentUrl = localUrl;
        var el = document.getElementById('status-indicator');
        el.textContent = '● OFFLINE CACHE';
        el.className = 'offline';
        console.log('[TileLayer] Switched to offline cache mode');
      }}
    }},

    _switchToOnline: function() {{
      if (isOffline) {{
        isOffline = false;
        failCount = 0;
        this._currentUrl = cdnUrl;
        var el = document.getElementById('status-indicator');
        el.textContent = '● CDN ONLINE';
        el.className = 'online';
        console.log('[TileLayer] Switched back to CDN mode');
      }}
    }},

    createTile: function(coords, done) {{
      var tile = L.TileLayer.prototype.createTile.call(this, coords, done);
      var self = this;

      tile.addEventListener('error', function() {{
        failCount++;
        if (failCount >= failThreshold && !isOffline) {{
          self._switchToOffline();
          // Force reload tiles from local cache
          self.redraw();
        }}
      }});

      tile.addEventListener('load', function() {{
        if (!isOffline) {{
          failCount = Math.max(0, failCount - 1);
        }}
      }});

      return tile;
    }}
  }});

  var tileLayer = new EsriFallbackLayer(cdnUrl, {{
    maxZoom: 19,
    maxNativeZoom: 17,
    attribution: 'Tiles &copy; Esri',
    crossOrigin: true,
    updateWhenZooming: false,
    updateWhenIdle: true,
    keepBuffer: 4
  }}).addTo(map);

  // Periodic online check (every 30s) to switch back if CDN recovers
  setInterval(function() {{
    if (isOffline) {{
      var img = new Image();
      img.onload = function() {{
        tileLayer._switchToOnline();
        tileLayer.redraw();
      }};
      img.onerror = function() {{ /* still offline */ }};
      img.src = cdnUrl.replace('{{z}}', '1').replace('{{y}}', '0').replace('{{x}}', '0') + '?t=' + Date.now();
    }}
  }}, 30000);

  // ---- Drone SVG Icon ----
  var droneSvg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40" class="drone-icon">
      <circle cx="20" cy="20" r="16" fill="none" stroke="rgba(0, 221, 255, 0.3)" stroke-width="1"/>
      <path d="M20 4 L26 28 L20 24 L14 28 Z"
            fill="rgba(0, 221, 255, 0.85)" stroke="#00ddff" stroke-width="1" stroke-linejoin="round"/>
      <path d="M12 18 L20 14 L28 18" fill="none" stroke="rgba(0, 221, 255, 0.6)" stroke-width="1"/>
      <circle cx="20" cy="18" r="2" fill="#ffffff" opacity="0.9"/>
    </svg>`;

  var droneIcon = L.divIcon({{
    html: droneSvg,
    className: '',
    iconSize: [40, 40],
    iconAnchor: [20, 20]
  }});

  // ---- Home Base Marker (Red Rock, NSW) ----
  var homeSvg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20">
      <circle cx="10" cy="10" r="6" fill="rgba(255, 100, 50, 0.7)" stroke="#ff6432" stroke-width="1.5"/>
      <circle cx="10" cy="10" r="2" fill="#ffffff" opacity="0.8"/>
    </svg>`;

  var homeIcon = L.divIcon({{
    html: homeSvg,
    className: '',
    iconSize: [20, 20],
    iconAnchor: [10, 10]
  }});

  L.marker([{center_lat}, {center_lon}], {{ icon: homeIcon, zIndexOffset: 500 }})
    .addTo(map)
    .bindTooltip('HOME — Red Rock, NSW', {{
      direction: 'right',
      offset: [12, 0],
      className: '',
      permanent: false,
      opacity: 0.9
    }});

  // ---- State ----
  var droneMarker = null;
  var trailCoords = [];
  var trailLine = null;
  var maxTrailPoints = 500;
  var followDrone = true;

  var trailStyle = {{
    color: 'rgba(0, 221, 255, 0.5)',
    weight: 2,
    opacity: 0.7,
    smoothFactor: 1
  }};

  trailLine = L.polyline([], trailStyle).addTo(map);

  // ---- User interaction ----
  map.on('dragstart', function() {{ followDrone = false; }});

  map.on('dblclick', function(e) {{
    if (droneMarker) {{
      followDrone = true;
      map.flyTo(droneMarker.getLatLng(), map.getZoom(), {{ duration: 0.8 }});
    }}
  }});

  map.on('click', function(e) {{
    if (e.originalEvent.altKey && bridge) {{
      // Setting a waypoint
      var lat = e.latlng.lat;
      var lon = e.latlng.lng;
      
      // Temporary marker for feedback
      L.circleMarker(e.latlng, {{ radius: 8, color: '#00ff78', fillOpacity: 0.5 }}).addTo(map)
        .bindTooltip("NAV TO: " + lat.toFixed(5) + ", " + lon.toFixed(5), {{ permanent: true, direction: 'top' }})
        .deleteOnTimeout(5000);
        
      bridge.on_map_click(lat, lon);
    }}
  }});
  
  L.Layer.prototype.deleteOnTimeout = function(ms) {{
    var self = this;
    setTimeout(function() {{ self.remove(); }}, ms);
    return this;
  }};

  // ---- Public API called from Python via runJavaScript ----
  function updateDronePosition(lat, lon, heading) {{
    var latlng = L.latLng(lat, lon);

    if (!droneMarker) {{
      droneMarker = L.marker(latlng, {{
        icon: droneIcon,
        zIndexOffset: 1000
      }}).addTo(map);
      map.setView(latlng, 13, {{ animate: false }});
      followDrone = true;
    }} else {{
      droneMarker.setLatLng(latlng);
    }}

    if (heading !== null && heading !== undefined) {{
      var iconEl = droneMarker._icon;
      if (iconEl) {{
        var svgEl = iconEl.querySelector('svg');
        if (svgEl) {{
          svgEl.style.transform = 'rotate(' + heading + 'deg)';
          svgEl.style.transformOrigin = 'center center';
        }}
      }}
    }}

    trailCoords.push([lat, lon]);
    if (trailCoords.length > maxTrailPoints) {{
      trailCoords = trailCoords.slice(-maxTrailPoints);
    }}
    trailLine.setLatLngs(trailCoords);

    if (followDrone) {{
      map.panTo(latlng, {{ animate: true, duration: 0.5 }});
    }}

  }}

  function clearTrail() {{
    trailCoords = [];
    trailLine.setLatLngs([]);
  }}

  function setMapCenter(lat, lon, zoom) {{
    map.flyTo([lat, lon], zoom, {{ duration: 1.2 }});
  }}

</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# SatelliteMapWidget
# ---------------------------------------------------------------------------

class MapBridge(QObject):
    """Bridge for JS -> Python communication."""
    waypoint_requested = Signal(float, float)

    @Slot(float, float)
    def on_map_click(self, lat, lon):
        self.waypoint_requested.emit(lat, lon)

class SatelliteMapWidget(QWidget):
    """
    Self-contained satellite map widget for the ISR Drone GCS.

    Tiles load directly from Esri CDN for speed. The local tile server
    runs as an automatic offline fallback.
    """
    
    waypoint_requested = Signal(float, float)

    # Default center: Red Rock, NSW
    DEFAULT_LAT = -29.983
    DEFAULT_LON = 153.233
    DEFAULT_ZOOM = 13

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tile_server = None
        self._web_view = None
        self._last_heading = 0.0
        self._bridge = MapBridge()
        self._bridge.waypoint_requested.connect(self.waypoint_requested.emit)
        
        self._setup_tile_server()
        self._setup_ui()

    def _setup_tile_server(self):
        """Start the local tile server (offline fallback)."""
        self._tile_server = LocalTileServer()
        self._tile_server.start()

    def _setup_ui(self):
        """Build the widget layout with the embedded map."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._web_view = QWebEngineView()
        self._web_view.setStyleSheet("background: #090e11; border: none;")

        html = _build_map_html(
            local_tile_url=self._tile_server.tile_url_template,
            center_lat=self.DEFAULT_LAT,
            center_lon=self.DEFAULT_LON,
            zoom=self.DEFAULT_ZOOM
        )
        self._web_view.setHtml(html, QUrl("http://127.0.0.1/"))

        self._channel = QWebChannel()
        self._channel.registerObject("bridge", self._bridge)
        self._web_view.page().setWebChannel(self._channel)

        layout.addWidget(self._web_view)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_drone_position(self, lat, lon, heading=None):
        """Move the drone marker to the given GPS coordinates."""
        if heading is not None:
            self._last_heading = heading
            hdg_arg = f"{heading}"
        else:
            hdg_arg = "null"

        js = f"updateDronePosition({lat}, {lon}, {hdg_arg});"
        self._web_view.page().runJavaScript(js)

    def set_center(self, lat, lon, zoom=None):
        """Pan/zoom the map to a specific location."""
        z = zoom if zoom is not None else self.DEFAULT_ZOOM
        js = f"setMapCenter({lat}, {lon}, {z});"
        self._web_view.page().runJavaScript(js)

    def clear_trail(self):
        """Clear the drone's flight trail from the map."""
        self._web_view.page().runJavaScript("clearTrail();")

    def cleanup(self):
        """Stop the tile server."""
        if self._tile_server:
            self._tile_server.stop()
