import socketio
import os
import json
import time
import uuid
import threading
import socket
from PySide6.QtCore import QObject, Slot

class BrainClient(QObject):
    def __init__(self, station_name="TrueGCS-Alpha", server_url="http://localhost:3001"):
        super().__init__()
        self.sio = socketio.Client()
        self.server_url = server_url
        
        # Load persistent identity 🛰️
        try:
            config_path = os.path.join(os.path.dirname(__file__), "fleet_config.json")
            print(f"Brain: Loading config from {config_path}")
            with open(config_path, "r") as f:
                config = json.load(f)
                # Generate professional computer-anchored identity 🛰️
                hostname = socket.gethostname().split('.')[0].upper()
                session_suffix = str(uuid.uuid4())[:4].upper()
                default_id = f"GCS-{hostname}-{session_suffix}"
                
                self.station_id = os.getenv("GCS_STATION_ID", default_id)
                self.station_name = os.getenv("GCS_STATION_NAME", default_id)
        except Exception as e:
            print(f"Brain: Config load failed: {e}")
            self.station_id = str(uuid.uuid4())
            self.station_name = station_name
            
        print(f"Brain: Station Identity -> {self.station_id} ({self.station_name})")
        self.connected = False
        
        # Telemetry storage for batching
        self.latest_telemetry = {} # { "sysid": { ...data... } }
        self.telemetry_lock = threading.Lock()
        
        # References to active MAVLink nodes for command execution
        self.nodes = {} # { node_id: TelemetryThread }
        
        # Video config storage
        self.video_config = {}

        # Socket.IO Event Handlers (Internal)
        @self.sio.event
        def connect():
            print(f"Brain: Connected to server at {self.server_url}")
            self.connected = True
            self._register() # Register immediately 🛰️

        @self.sio.event
        def disconnect():
            print("Brain: Disconnected from server")
            self.connected = False

        @self.sio.on('brain:command')
        def on_command(data):
            """
            Receives a command from the Brain and executes it on the GCS.
            Format: { "node_id": 1, "sysid": 1, "command": "arm", "params": {...} }
            """
            print(f"Brain: Received remote command: {data}")
            self._execute_command(data)

        @self.sio.on('*')
        def catch_all(event, data):
            # Ignore other events
            pass

    def register_node(self, node_id, thread):
        """Register a MAVLink thread so the brain can send commands to it."""
        self.nodes[node_id] = thread

    def _execute_command(self, data):
        node_id = data.get("node_id")
        sysid = data.get("sysid")
        cmd = data.get("command")
        params = data.get("params", {})

        if node_id not in self.nodes:
            print(f"Brain Error: Node {node_id} not found in GCS.")
            return

        tel = self.nodes[node_id]
        
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
                print(f"Brain Error: Unknown command '{cmd}'")
        except Exception as e:
            print(f"Brain Error: Failed to execute {cmd}: {e}")

    def _connect_thread(self):
        try:
            # Reconnection is True by default
            self.sio.connect(self.server_url, wait_timeout=10)
            self.sio.wait()
        except Exception as e:
            print(f"Brain: Connection failed or interrupted: {e}")

    def start(self):
        """Starts the connection in a background thread."""
        thread = threading.Thread(target=self._connect_thread, daemon=True)
        thread.start()
        
        # Start periodic telemetry and heartbeat emitters 🛰️
        self._start_timers()

    def _start_timers(self):
        def telemetry_loop():
            while True:
                time.sleep(2)
                self.emit_telemetry_batch()
        
        def heartbeat_loop():
            while True:
                time.sleep(10)
                self.emit_heartbeat()
                
        def identity_pulse_loop():
            while True:
                time.sleep(10)
                if self.connected:
                    self._register()
                
        threading.Thread(target=telemetry_loop, daemon=True).start()
        threading.Thread(target=heartbeat_loop, daemon=True).start()
        threading.Thread(target=identity_pulse_loop, daemon=True).start()

    def _register(self):
        """Emits brain:connect with station metadata."""
        if self.connected:
            self.sio.emit('brain:connect', {
                "station_id": self.station_id,
                "station_name": self.station_name
            })

    @Slot(int, int, float, float, float)
    def update_position(self, nid, sysid, lat, lon, alt):
        """Received from individual drone nodes via Signal."""
        # Unique key within this GCS is node_id_sysid
        sid_key = f"{nid}_{sysid}"
        
        with self.telemetry_lock:
            if sid_key not in self.latest_telemetry:
                self.latest_telemetry[sid_key] = {}
                
            self.latest_telemetry[sid_key].update({
                "lat": lat,
                "lng": lon,
                "lon": lon,
                "alt": alt
            })

    @Slot(int, int, float, float, float, str)
    def update_hud(self, nid, sysid, speed, battery, alt, mode):
        """Received from individual drone nodes via Signal."""
        sid_key = f"{nid}_{sysid}"
        
        with self.telemetry_lock:
            if sid_key not in self.latest_telemetry:
                self.latest_telemetry[sid_key] = {}
                
            self.latest_telemetry[sid_key].update({
                "speed": speed,
                "battery": battery,
                "alt": alt,
                "mode": mode,
                "sats": 0 # Placeholder if not in hud signal
            })

    def set_video_config(self, config):
        """
        config: { "port": 5008, "type": "UDP", "host": "0.0.0.0" }
        """
        self.video_config = config
        if self.connected:
            self.sio.emit('video:register', {
                "station_id": self.station_id,
                "video_config": config
            })

    def emit_telemetry_batch(self):
        """Emits the current telemetry batch (called every 2s)."""
        if not self.connected:
            return
            
        with self.telemetry_lock:
            if not self.latest_telemetry:
                # print(f"Brain: Skipping batch (Fleet Empty)")
                return
            
            # Emit full fleet map to prevent overwriting at the server 🛰️
            print(f"Brain: Pulsing Telemetry Batch for {len(self.latest_telemetry)} drones...")
            self.sio.emit('telemetry:batch', {
                "station_id": self.station_id,
                "telemetry": self.latest_telemetry
            })

    def emit_heartbeat(self):
        """Emits station:heartbeat (called every 10s)."""
        if self.connected:
            self.sio.emit('station:heartbeat', {
                "station_id": self.station_id
            })

    def stop(self):
        if self.sio.connected:
            self.sio.disconnect()
