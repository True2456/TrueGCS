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

        @self.sio.on('brain:command_relay')
        def on_command(data):
            """
            Receives a command from the Brain and executes it on the GCS.
            Format: { "station_id": "...", "drone_id": "nid_sysid", "command": "takeoff", "params": {...} }
            """
            # Only handle commands addressed to this station
            if data.get("station_id") != self.station_id:
                return
            print(f"Brain: Received remote command: {data}")
            self._execute_command(data)

        @self.sio.on('brain:mission_relay')
        def on_mission_relay(data):
            """
            Receives a survey mission from the Brain and uploads it to the target drone.
            Format: { "station_id": "...", "drone_id": "nid_sysid", "waypoints": [{lat,lng,alt,speed}] }
            """
            # Only handle missions addressed to this station
            if data.get("station_id") != self.station_id:
                return
            drone_id = data.get("drone_id", "")
            waypoints = data.get("waypoints", [])
            try:
                # drone_id is "nid_sysid" e.g. "0_1"
                parts = str(drone_id).split("_")
                nid = parts[0]          # string node id
                sysid = int(parts[1])   # MAVLink system id
            except (IndexError, ValueError):
                print(f"Brain: Invalid drone_id format: {drone_id}")
                return
            # Normalise field name: Brain sends 'lng', upload_mission expects 'lon'
            for wp in waypoints:
                if 'lng' in wp and 'lon' not in wp:
                    wp['lon'] = wp.pop('lng')
                if 'speed' not in wp:
                    wp['speed'] = 15  # sensible default m/s
            print(f"Brain: Mission relay → node={nid} sysid={sysid} ({len(waypoints)} waypoints)")
            if callable(self.on_mission_received):
                self.on_mission_received(nid, sysid, waypoints)

        @self.sio.on('*')
        def catch_all(event, data):
            # Ignore other events
            pass

        # Callback set externally by FleetBrainObserver
        self.on_mission_received = None

    def register_node(self, node_id, thread):
        """Register a MAVLink thread so the brain can send commands to it."""
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
            print(f"Brain Error: Invalid drone_id format: '{drone_id}'")
            return

        # self.nodes uses int keys sometimes, so try int first, then string
        tel = self.nodes.get(nid)
        if tel is None:
            try:
                tel = self.nodes.get(int(nid))
            except (ValueError, TypeError):
                pass
                
        if tel is None:
            print(f"Brain Error: Node '{nid}' not found in GCS. Available: {list(self.nodes.keys())}")
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
                time.sleep(1) # High-fidelity 1Hz pulse 🛰️
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
            
            # Sync tactical color if available 🛰️
            if nid in self.nodes:
                self.latest_telemetry[sid_key]["color"] = self.nodes[nid].color

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

            # Sync tactical color if available 🛰️
            if nid in self.nodes:
                self.latest_telemetry[sid_key]["color"] = self.nodes[nid].color

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
