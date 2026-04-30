import math
import json
import time
from PySide6.QtCore import QObject, QTimer, Signal
from telemetry.mavlink_thread import TelemetryThread
from video.video_thread import VideoThread
from core.brain_client import BrainClient

class ConnectionManager(QObject):
    status_msg = Signal(str, str) # text, color

    def __init__(self, window):
        super().__init__()
        self.window = window
        
        # State Storage
        self.telemetry_nodes = {}
        self.drone_headings = {}
        self.drone_armed = {}
        self.video_thread = None
        self.node_adding_lock = False
        
        # Fleet Brain Integration
        self.brain = BrainClient(station_name="TrueGCS-Master")
        self.brain.start()
        
        # Timers
        self.brain_telemetry_timer = QTimer()
        self.brain_telemetry_timer.timeout.connect(self.brain.emit_telemetry_batch)
        self.brain_telemetry_timer.start(2000)
        
        self.brain_heartbeat_timer = QTimer()
        self.brain_heartbeat_timer.timeout.connect(self.brain.emit_heartbeat)
        self.brain_heartbeat_timer.start(10000)

        # Config
        self.node_colors = ['#00ddff', '#ff3366', '#33ff55', '#ffaa00', '#aa00ff', '#ffffff']
        self.node_counter = 0
        self.vtol_modes = ["STABILIZE", "FBWA", "AUTO", "QLOITER", "QHOVER", "QRTL", "LOITER", "TAKEOFF", "TRANSITION", "CIRCLE", "RTL", "QLAND"]

    def add_new_node(self):
        if self.node_adding_lock:
            print("ConnectionManager: Connection attempt already in progress.")
            return

        try:
            ctype, device = self.window.combo_type.currentData()
            baud_rate = 115200
            try: baud_rate = int(self.window.txt_p1.text())
            except: pass
            
            self.node_adding_lock = True
            self.window.btn_add_node.setEnabled(False)
            
            self.node_counter += 1
            nid = self.node_counter
            color = self.node_colors[(nid - 1) % len(self.node_colors)]
            
            if ctype == "serial":
                tel = TelemetryThread(nid, color, connection_string=device, baud=baud_rate)
            elif ctype == "udp":
                port = self.window.txt_p1.text()
                tel = TelemetryThread(nid, color, connection_string=f"udpin:0.0.0.0:{port}")
            else:
                ip = self.window.txt_p1.text(); port = self.window.txt_p2.text()
                tel = TelemetryThread(nid, color, connection_string=f"{ctype}:{ip}:{port}")
                
            self.telemetry_nodes[nid] = tel
            self.brain.register_node(nid, tel) # Link to Brain
            self._connect_signals(tel)
            
            # Watcher for discovery
            def on_discovery(discovered_nid, sysid, c):
                if discovered_nid == nid:
                    self.node_adding_lock = False
                    self.window.btn_add_node.setEnabled(True)
                    self.status_msg.emit(f"MAVLink: Node {nid} Connected [Drone {sysid}]", color)
                    try: tel.signals.drone_discovered.disconnect(on_discovery)
                    except: pass

            tel.signals.drone_discovered.connect(on_discovery)
            tel.start()
            self.status_msg.emit(f"Connecting Node {nid}...", "orange")
            
            # Safety Timeout
            QTimer.singleShot(10000, lambda: self._handle_timeout(nid, tel))
            
        except Exception as e:
            self.node_counter -= 1
            self.node_adding_lock = False
            self.window.btn_add_node.setEnabled(True)
            self.status_msg.emit("Node Addition Failed", "red")
            print(f"ConnectionManager Error: {e}")

    def _handle_timeout(self, nid, tel):
        if self.node_adding_lock and nid in self.telemetry_nodes:
            if not tel.known_drones:
                self.telemetry_nodes.pop(nid).stop()
                self.node_counter -= 1
                self.node_adding_lock = False
                self.window.btn_add_node.setEnabled(True)
                self.status_msg.emit(f"Node {nid}: Connection Timeout", "red")

    def disconnect_active_node(self):
        nid, sid = self._get_active_target()
        if nid is not None and nid in self.telemetry_nodes:
            tel = self.telemetry_nodes.pop(nid)
            tel.stop()
            # UI Cleanup
            i = 0
            while i < self.window.combo_target_drone.count():
                data = self.window.combo_target_drone.itemData(i)
                if data and data["node_id"] == nid:
                    self.window.tab_ops.map_widget.remove_drone(nid, data["sysid"])
                    self.window.combo_target_drone.removeItem(i)
                else: i += 1
            
            if self.window.combo_target_drone.count() == 0:
                self.window.combo_target_drone.addItem("No Drones Detected", userData=None)
            self.status_msg.emit(f"Disconnected Node {nid}", "#ff3232")

    def _connect_signals(self, tel):
        tel.signals.drone_discovered.connect(self.window.r_drone_discovered)
        tel.signals.drone_lost.connect(self.window.r_drone_lost)
        tel.signals.hud_updated.connect(self.window.r_hud_updated)
        tel.signals.distance_sensor_updated.connect(self.window.r_distance_updated)
        tel.signals.gps2_updated.connect(self.window.r_gps2_updated)
        tel.signals.ekf_status_updated.connect(self.window.r_ekf_status_updated)
        tel.signals.nav_updated.connect(self.window.r_nav_updated)
        tel.signals.attitude_updated.connect(self.window.r_attitude_updated)
        tel.signals.position_updated.connect(self.window.r_position_updated)
        tel.signals.status_text_updated.connect(self.window.r_status_text)
        tel.signals.parameter_updated.connect(self.window.r_param_updated)
        tel.signals.parameters_loaded.connect(self.window.r_param_loaded)
        tel.signals.parameter_progress.connect(self.window.r_param_prog)
        tel.signals.modes_available.connect(self.window.r_modes_avail)
        tel.signals.armed_status_changed.connect(self.window.r_armed_status)
        
        # Brain Routing
        tel.signals.position_updated.connect(self.brain.update_position)
        tel.signals.hud_updated.connect(self.brain.update_hud)

    def _get_active_target(self):
        data = self.window.combo_target_drone.currentData()
        if data: return data["node_id"], data["sysid"]
        return None, None

    def toggle_video(self):
        if self.window.tab_ops.btn_vid_toggle.text() == "Start Video":
            if self.video_thread: self.video_thread.stop()
            vtype = self.window.tab_ops.combo_vid_type.currentText()
            vport = self.window.tab_ops.txt_vid_port.text().strip()
            host = self.window.tab_ops.txt_vid_ip.text().strip()
            
            src = int(vport) if (vport and vport.isdigit()) else 0
            if "UDP" in vtype:
                src = f"udp://{host or '0.0.0.0'}:{vport or '5008'}"
            
            self.video_thread = VideoThread(stream_url=src)
            from main import find_gstreamer
            self.video_thread.gst_path = find_gstreamer()
            self.window.tab_ops.video_label.video_thread = self.video_thread
            self.video_thread.frame_ready.connect(self.window.update_video_frame)
            self.video_thread.target_status.connect(self.window.tab_ops.update_target_status)
            self.video_thread.target_status.connect(lambda s, ox, oy, c: self.window.tab_ops.sensor_panel.update_vision(s, c, ox, oy))
            self.video_thread.source_frame_size.connect(self.window.tab_ops.video_label.set_source_frame_size)
            self.video_thread.tracking_error.connect(self.window.on_tracking_error)
            self.video_thread.ai_ready.connect(self.window.on_ai_ready)
            
            # AI Config
            eng = self.window.tab_video.combo_ai_engine.currentText().split()[0]
            mdl = self.window.tab_video.model_combo.currentText().split()[0]
            self.video_thread.set_ai_config(eng, mdl)
            self.video_thread.set_world_prompt(self.window.tab_video.txt_search_prompt.text())
            self.video_thread.set_ai_conf(self.window.tab_ops.slider_conf.value() / 100.0)
            self.video_thread.ai_diag_updated.connect(self.window.tab_ops.sensor_panel.update_ai_diagnostics)
            self.video_thread.start()
            
            self.window.tab_ops.btn_vid_toggle.setText("Stop Video")
            
            # Sync Video to Brain
            self.brain.set_video_config({
                "type": vtype,
                "port": vport or "5008",
                "host": host or "0.0.0.0"
            })
        else:
            if self.video_thread:
                self.video_thread.stop()
                self.video_thread = None
                self.window.tab_ops.video_label.video_thread = None
            self.window.mount_tracker.set_enabled(False)
            self.window.tab_ops.btn_vid_toggle.setText("Start Video")
            self.window.tab_ops.video_label.clear()

    def handle_mission_upload_request(self, target_id, wp_json):
        try:
            wps = json.loads(wp_json)
            nid, sid = self._parse_target(target_id)
            if nid in self.telemetry_nodes:
                self.telemetry_nodes[nid].upload_mission(sid, wps)
                self.status_msg.emit(f"Mission: Uploading {len(wps)} points to Drone {sid}...", "#00ddff")
        except Exception as e:
            print(f"Mission Upload Error: {e}")

    def handle_takeoff_request(self, target_id):
        try:
            nid, sid = self._parse_target(target_id)
            if nid in self.telemetry_nodes:
                self.telemetry_nodes[nid].send_takeoff(sid, alt=50.0)
                self.status_msg.emit(f"Mission: Initiating Takeoff (50m) for Drone {sid}...", "#ffaa00")
        except Exception as e:
            print(f"Takeoff Command Error: {e}")

    def handle_start_mission_request(self, target_id):
        try:
            nid, sid = self._parse_target(target_id)
            if nid in self.telemetry_nodes:
                self.telemetry_nodes[nid].start_mission(sid)
                self.status_msg.emit(f"Mission: Starting Autonomous Path for Drone {sid}...", "#00ff00")
        except Exception as e:
            print(f"Start Mission Error: {e}")

    def _parse_target(self, tid):
        if not tid or ":" not in tid: return None, None
        try:
            nid, sid = map(int, tid.split(":"))
            return nid, sid
        except: return None, None

    def on_gps_toggled(self, checked):
        nid, sid = self._get_active_target()
        if not nid: return
        tel = self.telemetry_nodes.get(nid)
        if tel:
            tel.set_gps_enabled(checked, is_gps2=False)

    def on_gps2_toggled(self, checked):
        nid, sid = self._get_active_target()
        if not nid: return
        tel = self.telemetry_nodes.get(nid)
        if tel:
            tel.set_gps_enabled(checked, is_gps2=True)
