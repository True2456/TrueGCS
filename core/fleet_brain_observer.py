from __future__ import annotations

from core.brain_client import BrainClient
from core.fleet_config import load_fleet_config, get_peer_sync, save_fleet_config
from PySide6.QtCore import QObject, Signal


# Distinct palette for peer (remote GCS) drones on the map
_PEER_COLORS = ["#ff66aa", "#66ffaa", "#ffcc66", "#66aaff", "#cc66ff", "#aaff66"]


class FleetBrainObserver(QObject):
    """
    Optional peer-GCS sync. Mirrors local telemetry to a Fleet Brain relay
    and can receive other stations' telemetry for display.
    Does not connect until apply_config(enabled=True) / start_from_config().
    """

    status_changed = Signal(str)

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.brain = None
        self._synced_nodes = set()
        self._peer_color_index = 0
        self._peer_colors = {}

    @property
    def connected(self) -> bool:
        return bool(self.brain and self.brain.connected)

    def start_from_config(self):
        peer = get_peer_sync()
        if peer.get("enabled"):
            self.connect_peer(peer)
        else:
            self.status_changed.emit("Peer sync disabled")

    def connect_peer(self, peer=None):
        peer = peer or get_peer_sync()
        self.disconnect_peer()
        if not peer.get("enabled"):
            self.status_changed.emit("Peer sync disabled")
            return

        self.brain = BrainClient.from_config(peer)
        self.brain.nodes = self.window.telemetry_nodes
        self.brain.on_mission_received = self.upload_search_mission
        self.brain.connection_changed.connect(self._on_connection)
        self.brain.status_message.connect(self.status_changed.emit)
        self.brain.peer_telemetry_updated.connect(self._on_peer_telemetry)

        self._synced_nodes.clear()
        for tel in list(self.window.telemetry_nodes.values()):
            self.sync_node(tel)

        self.brain.start()
        self.status_changed.emit(f"Connecting to {self.brain.server_url}…")

    def disconnect_peer(self):
        if self.brain:
            try:
                self.brain.stop()
            except Exception:
                pass
            self.brain = None
        self._synced_nodes.clear()
        self._clear_peer_markers()
        self.status_changed.emit("Peer sync offline")

    def apply_and_save(self, peer: dict, ai_safety: dict | None = None):
        cfg = load_fleet_config()
        cfg["peer_sync"] = peer
        if ai_safety is not None:
            cfg["ai_safety"] = ai_safety
        if peer.get("station_display_name"):
            cfg["station_name"] = peer["station_display_name"].strip()
        save_fleet_config(cfg)

        if peer.get("enabled"):
            if self.brain and self.brain.connected:
                needs_reconnect = self.brain.apply_settings(peer)
                if needs_reconnect:
                    self.connect_peer(peer)
                else:
                    self.status_changed.emit("Peer sync settings applied")
            else:
                self.connect_peer(peer)
        else:
            self.disconnect_peer()

    def _on_connection(self, connected: bool):
        if connected:
            self.status_changed.emit(f"Peer sync connected ({self.brain.server_url})")
        else:
            self.status_changed.emit("Peer sync disconnected")

    def sync_node(self, tel):
        """Wire a local MAVLink node into outbound peer telemetry."""
        if not self.brain:
            return
        key = id(tel)
        if key in self._synced_nodes:
            return
        self._synced_nodes.add(key)
        print(f"PeerSync: Linking node {tel.node_id}")
        tel.signals.position_updated.connect(self.brain.update_position)
        tel.signals.hud_updated.connect(self.brain.update_hud)
        self.brain.register_node(tel.node_id, tel)

    def upload_search_mission(self, nid, sysid, waypoints):
        if not self.brain or not self.brain.accept_remote_commands:
            print("PeerSync: Mission rejected — remote command receive disabled")
            return
        tel = self.window.telemetry_nodes.get(nid)
        if tel is None:
            try:
                tel = self.window.telemetry_nodes.get(int(nid))
            except (ValueError, TypeError):
                pass
        if tel is None:
            print(f"PeerSync: Mission rejected — node '{nid}' not found")
            return
        print(f"PeerSync: Uploading {len(waypoints)} waypoints to Node {nid} SysID {sysid}")
        tel.upload_mission(int(sysid), waypoints)

    def _peer_color(self, station_id: str) -> str:
        if station_id not in self._peer_colors:
            self._peer_colors[station_id] = _PEER_COLORS[self._peer_color_index % len(_PEER_COLORS)]
            self._peer_color_index += 1
        return self._peer_colors[station_id]

    def _on_peer_telemetry(self, station_id: str, telemetry: dict):
        """Plot remote GCS drones on the local map (receive path)."""
        if not hasattr(self.window, "tab_ops"):
            return
        map_widget = self.window.tab_ops.map_widget
        color = self._peer_color(station_id)
        for drone_key, data in (telemetry or {}).items():
            try:
                lat = float(data.get("lat", 0) or 0)
                lon = float(data.get("lng") or data.get("lon") or 0)
            except (TypeError, ValueError):
                continue
            if abs(lat) < 1e-8 and abs(lon) < 1e-8:
                continue
            # Synthetic node ids for peers: hash station into negative range-ish ints via string keys
            # Map API expects node_id + sysid — use string-safe synthetic ids via hash
            try:
                parts = str(drone_key).split("_")
                local_nid, local_sid = int(parts[0]), int(parts[1])
            except (ValueError, IndexError):
                local_nid, local_sid = 9000, abs(hash(drone_key)) % 1000

            # Offset node_id into a peer namespace so we don't collide with local nodes
            peer_nid = 10000 + (abs(hash(station_id)) % 1000) + local_nid
            heading = data.get("heading")
            try:
                map_widget.update_drone_position(
                    peer_nid, local_sid, lat, lon,
                    heading=heading, color=color
                )
            except Exception as e:
                print(f"PeerSync: map update failed: {e}")

            if hasattr(self.window.tab_ops, "cesium_widget"):
                try:
                    alt = float(data.get("alt") or 0)
                    hdg = float(heading or 0)
                    self.window.tab_ops.cesium_widget.update_drone_position(
                        peer_nid, local_sid, lat, lon, alt, hdg, color=color
                    )
                except Exception:
                    pass

    def _clear_peer_markers(self):
        # Soft clear: map keeps last positions until overwritten; no global clear API for peers
        self._peer_colors.clear()
