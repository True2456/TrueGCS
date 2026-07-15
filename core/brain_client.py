import socketio
import os
import json
import time
import threading
from PySide6.QtCore import QObject, Signal, Slot

from core.fleet_config import load_fleet_config, get_peer_sync


class BrainClient(QObject):
    """Socket.IO client for peer-GCS sync via the Fleet Brain relay server."""

    peer_telemetry_updated = Signal(str, object)  # station_id, telemetry dict
    connection_changed = Signal(bool)
    status_message = Signal(str)

    def __init__(
        self,
        station_name="TrueGCS-Alpha",
        server_url="http://127.0.0.1:3001",
        shared_secret="",
        transmit_telemetry=True,
        transmit_video=False,
        receive_peer_telemetry=True,
        accept_remote_commands=False,
        station_id=None,
    ):
        super().__init__()
        self.sio = socketio.Client(reconnection=True, reconnection_attempts=0)
        self.server_url = server_url
        self.shared_secret = shared_secret or ""
        self.transmit_telemetry = transmit_telemetry
        self.transmit_video = transmit_video
        self.receive_peer_telemetry = receive_peer_telemetry
        self.accept_remote_commands = accept_remote_commands

        cfg = load_fleet_config()
        self.station_id = station_id or cfg.get("station_id") or station_name
        self.station_name = station_name or cfg.get("station_name") or self.station_id

        print(f"PeerSync: Station Identity -> {self.station_id} ({self.station_name})")
        self.connected = False
        self._running = False
        self._timers_started = False

        self.latest_telemetry = {}
        self.telemetry_lock = threading.Lock()
        self.nodes = {}
        self.video_config = {}
        self.on_mission_received = None

        self._bind_socket_handlers()

    @classmethod
    def from_config(cls, peer=None):
        cfg = load_fleet_config()
        peer = peer or get_peer_sync(cfg)
        display = (peer.get("station_display_name") or "").strip() or cfg.get("station_name")
        return cls(
            station_name=display,
            server_url=(peer.get("server_url") or "http://127.0.0.1:3001").strip(),
            shared_secret=peer.get("shared_secret") or "",
            transmit_telemetry=bool(peer.get("transmit_telemetry", True)),
            transmit_video=bool(peer.get("transmit_video", False)),
            receive_peer_telemetry=bool(peer.get("receive_peer_telemetry", True)),
            accept_remote_commands=bool(peer.get("accept_remote_commands", False)),
            station_id=cfg.get("station_id"),
        )

    def apply_settings(self, peer: dict):
        """Update runtime flags without tearing down (URL/secret need reconnect)."""
        self.transmit_telemetry = bool(peer.get("transmit_telemetry", True))
        self.transmit_video = bool(peer.get("transmit_video", False))
        self.receive_peer_telemetry = bool(peer.get("receive_peer_telemetry", True))
        self.accept_remote_commands = bool(peer.get("accept_remote_commands", False))
        display = (peer.get("station_display_name") or "").strip()
        if display:
            self.station_name = display
        new_url = (peer.get("server_url") or "").strip()
        new_secret = peer.get("shared_secret") or ""
        needs_reconnect = (
            new_url and new_url != self.server_url
        ) or (new_secret != self.shared_secret)
        if new_url:
            self.server_url = new_url
        self.shared_secret = new_secret
        return needs_reconnect

    def _auth_payload(self):
        return {"shared_secret": self.shared_secret} if self.shared_secret else {}

    def _bind_socket_handlers(self):
        @self.sio.event
        def connect():
            print(f"PeerSync: Connected to {self.server_url}")
            self.connected = True
            self.connection_changed.emit(True)
            self.status_message.emit(f"Connected to {self.server_url}")
            self._register()

        @self.sio.event
        def connect_error(data):
            print(f"PeerSync: Connect error: {data}")
            self.status_message.emit(f"Connect error: {data}")

        @self.sio.event
        def disconnect():
            print("PeerSync: Disconnected")
            self.connected = False
            self.connection_changed.emit(False)
            self.status_message.emit("Disconnected")

        @self.sio.on("brain:command_relay")
        def on_command(data):
            if not self.accept_remote_commands:
                return
            if data.get("station_id") != self.station_id:
                return
            print(f"PeerSync: Received remote command: {data.get('command')}")
            self._execute_command(data)

        @self.sio.on("brain:mission_relay")
        def on_mission_relay(data):
            if not self.accept_remote_commands:
                print("PeerSync: Ignoring mission relay (accept_remote_commands=off)")
                return
            if data.get("station_id") != self.station_id:
                return
            drone_id = data.get("drone_id", "")
            waypoints = data.get("waypoints", [])
            try:
                parts = str(drone_id).split("_")
                nid = parts[0]
                sysid = int(parts[1])
            except (IndexError, ValueError):
                print(f"PeerSync: Invalid drone_id format: {drone_id}")
                return
            for wp in waypoints:
                if "lng" in wp and "lon" not in wp:
                    wp["lon"] = wp.pop("lng")
                if "speed" not in wp:
                    wp["speed"] = 15
            print(f"PeerSync: Mission relay → node={nid} sysid={sysid} ({len(waypoints)} wps)")
            if callable(self.on_mission_received):
                self.on_mission_received(nid, sysid, waypoints)

        @self.sio.on("telemetry:update")
        def on_peer_telemetry(data):
            if not self.receive_peer_telemetry:
                return
            station_id = data.get("stationId") or data.get("station_id")
            if not station_id or station_id == self.station_id:
                return
            telemetry = data.get("telemetry") or {}
            self.peer_telemetry_updated.emit(str(station_id), telemetry)

    def register_node(self, node_id, thread):
        self.nodes[node_id] = thread

    def _execute_command(self, data):
        drone_id = data.get("drone_id", "")
        cmd = data.get("command")
        params = data.get("params", {})

        try:
            parts = str(drone_id).split("_")
            nid = parts[0]
            sysid = int(parts[1])
        except (IndexError, ValueError):
            print(f"PeerSync Error: Invalid drone_id format: '{drone_id}'")
            return

        tel = self.nodes.get(nid)
        if tel is None:
            try:
                tel = self.nodes.get(int(nid))
            except (ValueError, TypeError):
                pass

        if tel is None:
            print(f"PeerSync Error: Node '{nid}' not found. Available: {list(self.nodes.keys())}")
            return

        try:
            if cmd == "arm":
                tel.arm(sysid, params.get("armed", True))
            elif cmd == "takeoff":
                tel.send_takeoff(sysid, params.get("altitude", 50.0))
            elif cmd == "goto":
                tel.set_waypoint(sysid, params.get("lat"), params.get("lng"), params.get("alt", 50.0))
            elif cmd == "set_mode":
                tel.set_flight_mode(sysid, params.get("mode", "AUTO"))
            elif cmd == "start_mission":
                tel.start_mission(sysid)
            else:
                print(f"PeerSync Error: Unknown command '{cmd}'")
        except Exception as e:
            print(f"PeerSync Error: Failed to execute {cmd}: {e}")

    def _connect_thread(self):
        while self._running:
            try:
                auth = self._auth_payload()
                self.sio.connect(
                    self.server_url,
                    wait_timeout=10,
                    auth=auth,
                    headers={"x-gcs-secret": self.shared_secret} if self.shared_secret else {},
                )
                self.sio.wait()
            except Exception as e:
                print(f"PeerSync: Connection failed or interrupted: {e}")
                self.status_message.emit(f"Connection failed: {e}")
                self.connected = False
                self.connection_changed.emit(False)
            if self._running:
                time.sleep(3)

    def start(self):
        if self._running:
            return
        self._running = True
        thread = threading.Thread(target=self._connect_thread, daemon=True, name="PeerSyncConnect")
        thread.start()
        self._start_timers()

    def stop(self):
        self._running = False
        try:
            if self.sio.connected:
                try:
                    self.sio.emit("station:remove", self.station_id)
                except Exception:
                    pass
                self.sio.disconnect()
        except Exception:
            pass
        self.connected = False
        self.connection_changed.emit(False)

    def _start_timers(self):
        if self._timers_started:
            return
        self._timers_started = True

        def telemetry_loop():
            while self._running:
                time.sleep(1)
                self.emit_telemetry_batch()

        def heartbeat_loop():
            while self._running:
                time.sleep(10)
                self.emit_heartbeat()

        def identity_pulse_loop():
            while self._running:
                time.sleep(10)
                if self.connected:
                    self._register()

        threading.Thread(target=telemetry_loop, daemon=True).start()
        threading.Thread(target=heartbeat_loop, daemon=True).start()
        threading.Thread(target=identity_pulse_loop, daemon=True).start()

    def _register(self):
        if self.connected:
            payload = {
                "station_id": self.station_id,
                "station_name": self.station_name,
            }
            if self.shared_secret:
                payload["shared_secret"] = self.shared_secret
            self.sio.emit("brain:connect", payload)

    @Slot(int, int, float, float, float)
    def update_position(self, nid, sysid, lat, lon, alt):
        if not self.transmit_telemetry:
            return
        sid_key = f"{nid}_{sysid}"
        with self.telemetry_lock:
            if sid_key not in self.latest_telemetry:
                self.latest_telemetry[sid_key] = {}
            self.latest_telemetry[sid_key].update({
                "lat": lat,
                "lng": lon,
                "lon": lon,
                "alt": alt,
            })
            if nid in self.nodes:
                self.latest_telemetry[sid_key]["color"] = self.nodes[nid].color

    @Slot(int, int, float, float, float, str)
    def update_hud(self, nid, sysid, speed, battery, alt, mode):
        if not self.transmit_telemetry:
            return
        sid_key = f"{nid}_{sysid}"
        with self.telemetry_lock:
            if sid_key not in self.latest_telemetry:
                self.latest_telemetry[sid_key] = {}
            self.latest_telemetry[sid_key].update({
                "speed": speed,
                "battery": battery,
                "alt": alt,
                "mode": mode,
                "sats": 0,
            })
            if nid in self.nodes:
                self.latest_telemetry[sid_key]["color"] = self.nodes[nid].color

    def set_video_config(self, config):
        self.video_config = config
        if self.connected and self.transmit_video:
            self.sio.emit("video:register", {
                "station_id": self.station_id,
                "video_config": config,
            })

    def emit_telemetry_batch(self):
        if not self.connected or not self.transmit_telemetry:
            return
        with self.telemetry_lock:
            if not self.latest_telemetry:
                return
            self.sio.emit("telemetry:batch", {
                "station_id": self.station_id,
                "telemetry": self.latest_telemetry,
            })

    def emit_heartbeat(self):
        if self.connected:
            self.sio.emit("station:heartbeat", {
                "station_id": self.station_id,
            })

    def emit_video_status(self, active, source=""):
        if not self.connected or not self.transmit_video:
            return
        self.sio.emit("video:status", {
            "station_id": self.station_id,
            "active": active,
            "source": source,
        })

    def can_relay_video(self) -> bool:
        return bool(self.connected and self.transmit_video)
