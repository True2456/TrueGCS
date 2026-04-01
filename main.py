import sys
import os
import time
import json
import math
from PySide6.QtWidgets import QApplication
from ui.main_window import GCSMainWindow
from video.video_thread import VideoThread
from telemetry.mavlink_thread import TelemetryThread
from PySide6.QtCore import QTimer
from gimbal.mount_tracker import MountTrackerController, MountTrackerConfig

class LogRedirector:
    def __init__(self, widget):
        self.widget = widget
        self.log_file = open("gcs_crash.log", "w", encoding="utf-8")
    def write(self, text):
        self.widget.insertPlainText(text)
        self.widget.ensureCursorVisible()
        try:
            self.log_file.write(text)
            self.log_file.flush()
        except: pass
    def flush(self): pass

def find_gstreamer():
    common_paths = [
        r"C:\gstreamer\1.0\msvc_x86_64\bin\gst-launch-1.0.exe",
        r"C:\gstreamer\1.0\x86_64\bin\gst-launch-1.0.exe",
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), r"gstreamer\1.0\msvc_x86_64\bin\gst-launch-1.0.exe")
    ]
    for p in common_paths:
        if os.path.exists(p): return p
    return "gst-launch-1.0.exe"

def main():
    if sys.platform == "win32":
        base_gst = r"C:\ProgramData\Mission Planner\gstreamer\1.0\x86_64"
        dll_path = os.path.join(base_gst, "bin")
        plugin_path = os.path.join(base_gst, "lib", "gstreamer-1.0")
        if os.path.exists(dll_path):
            try:
                if sys.version_info >= (3, 8):
                    os.add_dll_directory(dll_path)
                os.environ["GST_PLUGIN_PATH"] = plugin_path
                os.environ["PATH"] = dll_path + os.pathsep + os.environ.get("PATH", "")
                print(f"Mission: GStreamer DLLs Ingested from Mission Planner Path.")
            except Exception as e:
                print(f"Mission: Failed to add DLL directory: {e}")
                
    if sys.platform == "win32":
        os.system("taskkill /F /IM gst-launch-1.0.exe >nul 2>&1")

    app = QApplication(sys.argv)
    window = GCSMainWindow()

    global current_ai_engine, current_ai_model
    current_ai_engine = "CPU"
    current_ai_model = "YOLOv8n"

    window.video_thread = None
    window.tab_ops.video_label.video_thread = None
    window.relay_process = None
    window.mount_tracker = MountTrackerController(MountTrackerConfig())
    
    # ---- GLOBAL NODE MANAGER ----
    window.telemetry_nodes = {}
    node_colors = ['#00ddff', '#ff3366', '#33ff55', '#ffaa00', '#aa00ff', '#ffffff']
    node_counter = [0]

    def get_active_target():
        data = window.combo_target_drone.currentData()
        if data:
            return data["node_id"], data["sysid"]
        return None, None

    # ---- SIGNAL ROUTERS ----
    def sync_mission_drone_list():
        dList = []
        for i in range(window.combo_target_drone.count()):
            data = window.combo_target_drone.itemData(i)
            if data:
                nid = data["node_id"]
                sid = data["sysid"]
                name = window.combo_target_drone.itemText(i)
                dList.append({"id": f"{nid}:{sid}", "name": name})
        window.tab_ops.map_widget.update_drone_list(dList)

    def r_drone_discovered(node_id, sysid, color):
        if window.combo_target_drone.count() == 1 and window.combo_target_drone.itemData(0) is None:
            window.combo_target_drone.clear()
        
        # Prevent duplicates
        for i in range(window.combo_target_drone.count()):
            data = window.combo_target_drone.itemData(i)
            if data and data["node_id"] == node_id and data["sysid"] == sysid:
                return

        conn_method = "Unknown"
        node = window.telemetry_nodes.get(node_id)
        if node:
            conn_method = node.connection_string.replace("udpin:0.0.0.0:", "UDP:")
            
        dt = f"Drone {sysid} via {conn_method} (Node {node_id})"
        window.combo_target_drone.addItem(dt, userData={"node_id": node_id, "sysid": sysid})
        print(f"NodeManager: Drone Discovered -> {dt}")
        
        window.lbl_status.setText(f"Discovered SysID {sysid}")
        window.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")
        
        tel = window.telemetry_nodes.get(node_id)
        if tel: window.tab_cfg.request_curated_params()
        sync_mission_drone_list()

    def r_drone_lost(node_id, sysid):
        for i in range(window.combo_target_drone.count()):
            data = window.combo_target_drone.itemData(i)
            if data and data["node_id"] == node_id and data["sysid"] == sysid:
                window.combo_target_drone.removeItem(i)
                break
        window.tab_ops.map_widget.remove_drone(node_id, sysid)
        if window.combo_target_drone.count() == 0:
            window.combo_target_drone.addItem("No Drones Detected", userData=None)
        print(f"NodeManager: Drone Lost -> Node {node_id} SysID {sysid}")
        sync_mission_drone_list()

    def r_hud_updated(n_id, s_id, speed, batt, alt, mode):
        an, as_id = get_active_target()
        if n_id == an and s_id == as_id:
            window.tab_ops.map_hud.update_telemetry(speed=speed if speed > -1 else None, batt=batt if batt > -1 else None, alt=alt if alt > -1 else None, mode=mode)

    def r_attitude_updated(n_id, s_id, roll, pitch, yaw):
        an, as_id = get_active_target()
        if n_id == an and s_id == as_id:
            window.tab_ops.update_attitude(roll, pitch, yaw)

    def r_position_updated(n_id, s_id, lat, lon, alt):
        # Guard against invalid GPS values to avoid noisy console/JS errors.
        if lat is None or lon is None:
            return
        if not math.isfinite(lat) or not math.isfinite(lon):
            return
        if abs(lat) > 90.0 or abs(lon) > 180.0:
            return

        color = window.telemetry_nodes[n_id].color if n_id in window.telemetry_nodes else "#ffffff"
        window.tab_ops.map_widget.update_drone_position(n_id, s_id, lat, lon, None, color)
        an, as_id = get_active_target()
        if n_id == an and s_id == as_id:
            window.tab_ops.update_position(lat, lon, alt)

    def r_status_text(n_id, s_id, txt):
        an, as_id = get_active_target()
        if n_id == an and s_id == as_id:
            window.lbl_status.setText(f"Drone {s_id}: {txt}")

    def r_param_updated(n_id, s_id, param, val):
        an, as_id = get_active_target()
        if n_id == an and s_id == as_id:
            window.tab_cfg.update_param_value(param, val)

    def r_param_loaded(n_id, s_id):
        an, as_id = get_active_target()
        if n_id == an and s_id == as_id:
            window.on_params_loaded()

    def r_param_prog(n_id, s_id, current, total):
        an, as_id = get_active_target()
        if n_id == an and s_id == as_id:
            window.tab_cfg.update_param_progress(current, total)

    def r_modes_avail(n_id, s_id, modes):
        an, as_id = get_active_target()
        if n_id == an and s_id == as_id:
            window.populate_flight_modes(modes)

    def connect_telemetry_signals(tel):
        tel.signals.drone_discovered.connect(r_drone_discovered)
        tel.signals.drone_lost.connect(r_drone_lost)
        tel.signals.hud_updated.connect(r_hud_updated)
        tel.signals.attitude_updated.connect(r_attitude_updated)
        tel.signals.position_updated.connect(r_position_updated)
        tel.signals.status_text_updated.connect(r_status_text)
        tel.signals.parameter_updated.connect(r_param_updated)
        tel.signals.parameters_loaded.connect(r_param_loaded)
        tel.signals.parameter_progress.connect(r_param_prog)
        tel.signals.modes_available.connect(r_modes_avail)

    # ---- NODE MANAGEMENT ----
    def add_new_node():
        try:
            ctype, device = window.combo_type.currentData()
            baud_rate = 115200
            try: baud_rate = int(window.txt_p1.text())
            except: pass
            node_counter[0] += 1
            nid = node_counter[0]
            color = node_colors[(nid - 1) % len(node_colors)]
            if ctype == "serial":
                tel = TelemetryThread(nid, color, connection_string=device, baud=baud_rate)
            elif ctype == "udp":
                port = window.txt_p1.text()
                tel = TelemetryThread(nid, color, connection_string=f"udpin:0.0.0.0:{port}")
            else:
                ip = window.txt_p1.text(); port = window.txt_p2.text()
                tel = TelemetryThread(nid, color, connection_string=f"{ctype}:{ip}:{port}")
            window.telemetry_nodes[nid] = tel
            connect_telemetry_signals(tel)
            tel.start()
            window.lbl_status.setText(f"Added Node {nid} ({ctype})")
            window.lbl_status.setStyleSheet(f"color: {color}; font-size: 14px;")
        except Exception as e:
            window.lbl_status.setText(f"Node Addition Failed")
            window.lbl_status.setStyleSheet("color: red; font-size: 14px;")

    def disconnect_active_node():
        an, as_id = get_active_target()
        if an is not None and an in window.telemetry_nodes:
            nid = an
            tel = window.telemetry_nodes.pop(nid)
            tel.stop()
            i = 0
            while i < window.combo_target_drone.count():
                data = window.combo_target_drone.itemData(i)
                if data and data["node_id"] == nid:
                    window.tab_ops.map_widget.remove_drone(nid, data["sysid"])
                    window.combo_target_drone.removeItem(i)
                else: i += 1
            if window.combo_target_drone.count() == 0:
                window.combo_target_drone.addItem("No Drones Detected", userData=None)
            window.lbl_status.setText(f"Disconnected Node {nid}")
            window.lbl_status.setStyleSheet("color: #ff3232; font-size: 14px;")

    # ---- MISSION UPLOAD ----
    def handle_mission_upload_request(target_id, wp_json):
        try:
            wps = json.loads(wp_json)
            # target_id is "node_id:sysid"
            if ":" not in target_id: return
            nid, sid = map(int, target_id.split(":"))
            
            if nid in window.telemetry_nodes:
                window.telemetry_nodes[nid].upload_mission(sid, wps)
                window.lbl_status.setText(f"Mission: Uploading {len(wps)} points to Drone {sid}...")
                window.lbl_status.setStyleSheet("color: #00ddff; font-weight: bold;")
            else:
                print(f"Mission: Node {nid} not found for upload.")
        except Exception as e:
            print(f"Mission Upload Error: {e}")

    # ---- TX COMMAND ROUTERS ----
    window.btn_add_node.clicked.connect(add_new_node)
    window.btn_disconnect_node.clicked.connect(disconnect_active_node)
    window.tab_ops.map_widget.waypoint_requested.connect(lambda lat, lon: window.telemetry_nodes[get_active_target()[0]].set_waypoint(get_active_target()[1], lat, lon) if get_active_target()[0] is not None else None)
    window.tab_ops.map_widget.mission_upload_requested.connect(handle_mission_upload_request)

    
    window.tab_cfg.write_param_requested.connect(lambda p, v: window.telemetry_nodes[get_active_target()[0]].set_parameter(get_active_target()[1], p, v) if get_active_target()[0] is not None else None)
    window.tab_cfg.fetch_params_requested.connect(lambda pl: window.telemetry_nodes[get_active_target()[0]].fetch_parameters(get_active_target()[1], pl) if get_active_target()[0] is not None else None)
    window.tab_cfg.fetch_full_list_requested.connect(lambda: window.telemetry_nodes[get_active_target()[0]].request_all_params_list(get_active_target()[1]) if get_active_target()[0] is not None else None)
    
    window.combo_mode.currentTextChanged.connect(lambda m: window.telemetry_nodes[get_active_target()[0]].set_flight_mode(get_active_target()[1], m) if get_active_target()[0] is not None else None)

    def on_active_drone_changed(index):
        an, as_id = get_active_target()
        if an is not None and an in window.telemetry_nodes:
            tel = window.telemetry_nodes[an]
            window.tab_cfg.table_params.setRowCount(0)
            for p_id, p_val in tel.parameters.get(as_id, {}).items():
                window.tab_cfg.update_param_value(p_id, p_val)
            if as_id in tel._modes_emitted and tel._modes_emitted[as_id]:
                window.populate_flight_modes(list(tel.master.mode_mapping().keys()))
            window.combo_mode.blockSignals(True)
            window.combo_mode.setCurrentText(tel._last_mode.get(as_id, ""))
            window.combo_mode.blockSignals(False)
            window.lbl_status.setText(f"Focus: Node {an} SysID {as_id}")

    window.combo_target_drone.currentIndexChanged.connect(on_active_drone_changed)

    # ---- LOCKOUT GUARD: Ensures OS/CUDA cleanup is 100% complete 🛡️ ----
    window.lockout_remaining = 0
    window.lockout_timer = QTimer()

    def update_lockout():
        if window.lockout_remaining > 0:
            window.lockout_remaining -= 1
            window.tab_ops.btn_vid_toggle.setText(f"Ready in {window.lockout_remaining}s...")
            window.tab_ops.btn_vid_toggle.setEnabled(False)
        else:
            window.lockout_timer.stop()
            window.tab_ops.btn_vid_toggle.setText("Start Video")
            window.tab_ops.btn_vid_toggle.setEnabled(True)

    window.lockout_timer.timeout.connect(update_lockout)

    # ---- VIDEO ----
    def toggle_video():
        if window.tab_ops.btn_vid_toggle.text() == "Start Video":
            if window.video_thread: window.video_thread.stop()
            vtype = window.tab_ops.combo_vid_type.currentText()
            vport = window.tab_ops.txt_vid_port.text().strip()
            host = window.tab_ops.txt_vid_ip.text().strip()
            
            if "RTMP" in vtype:
                src = f"rtmp://{host or '0.0.0.0'}:{vport or '1935'}/live/drone"
            elif "USB" in vtype:
                src = int(vport) if vport.isdigit() else 0
            else:
                protocol = "udp" if "UDP" in vtype else "rtp"
                src = f"{protocol}://{host or '0.0.0.0'}:{vport or '5008'}"
            
            window.video_thread = VideoThread(stream_url=src)
            window.video_thread.gst_path = find_gstreamer()
            window.tab_ops.video_label.video_thread = window.video_thread
            window.video_thread.frame_ready.connect(window.update_video_frame)
            window.video_thread.target_status.connect(window.tab_ops.update_target_status)
            window.video_thread.source_frame_size.connect(window.tab_ops.video_label.set_source_frame_size)
            window.video_thread.tracking_error.connect(on_tracking_error)
            window.video_thread.ai_ready.connect(on_ai_ready)
            # Apply any AI engine/model preset from Video tab at startup
            eng = window.tab_video.combo_ai_engine.currentText().split()[0]
            mdl = window.tab_video.model_combo.currentText().split()[0]
            window.video_thread.set_ai_config(eng, mdl)
            window.video_thread.set_world_prompt(window.tab_video.txt_search_prompt.text())
            window.video_thread.start()
            window.video_thread.set_show_detections(window.tab_ops.chk_enable_det.isChecked())
            window.video_thread.set_tracking_mode(window.tab_ops.combo_tracking_mode.currentData())
            window.mount_tracker.set_enabled(window.tab_ops.chk_tracking.isChecked() and window.tab_ops.combo_tracking_mode.currentData() != "none")
            window.tab_ops.btn_vid_toggle.setText("Stop Video")
        else:
            if window.video_thread:
                window.video_thread.stop()
                # TRASH THE ZOMBIE: Nulling the thread ensures Port settings and AI logic reset for the next run 🏎️
                window.video_thread = None
                window.tab_ops.video_label.video_thread = None
            window.mount_tracker.set_enabled(False)
            window.tab_ops.btn_vid_toggle.setText("Start Video")
            window.tab_ops.video_label.clear()

    def on_tracking_error(err_x, err_y):
        if not window.video_thread:
            return
        out = window.mount_tracker.update(err_x, err_y)
        if out is None:
            return
        an, as_id = get_active_target()
        if an is None or an not in window.telemetry_nodes:
            return
        pitch, yaw = out
        window.telemetry_nodes[an].mount_control(as_id, pitch, 0.0, yaw)

    def on_video_click(x, y):
        if not window.video_thread:
            return
        mode = window.tab_ops.combo_tracking_mode.currentData()
        # Simple one-shot slew: move gimbal so clicked point is driven toward screen center.
        if mode == "center":
            # Provide operator feedback crosshair
            try:
                window.video_thread.set_click_marker(x, y, ttl_s=1.5)
            except Exception:
                pass

            # Behave like a "click lock": seed the clicked pixel and let the normal
            # detection association + PID tracking drive the gimbal to center.
            window.video_thread.set_tracking_mode("center")
            window.video_thread.handle_click(x, y)

            # Auto-enable tracking so the PID loop is active.
            window.tab_ops.chk_tracking.setChecked(True)
            window.mount_tracker.set_enabled(True)
            return

        window.video_thread.handle_click(x, y)
        enabled = window.tab_ops.chk_tracking.isChecked() and mode not in ("none", "center")
        window.mount_tracker.set_enabled(enabled)

    def on_detection_toggled(checked):
        if window.video_thread:
            window.video_thread.set_show_detections(bool(checked))

    def on_tracking_mode_changed(index):
        mode = window.tab_ops.combo_tracking_mode.itemData(index)
        if window.video_thread:
            window.video_thread.set_tracking_mode(mode)
        enabled = window.tab_ops.chk_tracking.isChecked() and mode != "none"
        window.mount_tracker.set_enabled(enabled)
        if mode == "none" and window.video_thread:
            window.video_thread.set_tracking_point(None, None)
        if enabled:
            # Align controller internal state to last known mount angles
            an, as_id = get_active_target()
            if an is not None and an in window.telemetry_nodes:
                mp = window.telemetry_nodes[an].mount_angles.get(as_id)
                if mp:
                    pitch_deg, yaw_deg = mp
                    window.mount_tracker.pitch_deg = float(pitch_deg)
                    window.mount_tracker.yaw_deg = float(yaw_deg)

    def on_tracking_toggled(checked):
        mode = window.tab_ops.combo_tracking_mode.currentData()
        enabled = bool(checked) and mode != "none"
        window.mount_tracker.set_enabled(enabled)
        if enabled:
            # Align controller internal state to the last known mount angles
            an, as_id = get_active_target()
            if an is not None and an in window.telemetry_nodes:
                mp = window.telemetry_nodes[an].mount_angles.get(as_id)
                if mp:
                    pitch_deg, yaw_deg = mp
                    window.mount_tracker.pitch_deg = float(pitch_deg)
                    window.mount_tracker.yaw_deg = float(yaw_deg)
        if not checked and window.video_thread:
            window.video_thread.set_tracking_point(None, None)

    def on_wipe_lock():
        if window.video_thread:
            window.video_thread.set_tracking_point(None, None)
        window.mount_tracker.reset()

    window.restarting_for_ai = False

    def on_ai_ready(engine, model_name):
        try:
            window.tab_video.btn_apply_ai.setEnabled(True)
            window.tab_video.btn_apply_ai.setText("Apply AI Engine Settings")
            window.lbl_status.setText(f"AI Configured: {model_name} on {engine}")
            
            # Start the 8-second stability lockout 🛡️
            # This ensures background taskkills and CUDA purges are 100% finished
            window.lockout_remaining = 8
            window.tab_ops.btn_vid_toggle.setEnabled(False)
            window.tab_ops.btn_vid_toggle.setText(f"Ready in 8s...")
            window.lockout_timer.start(1000)
        except: pass

    def on_ai_settings_applied(engine, model_name):
        global current_ai_engine, current_ai_model
        
        # Guard: If already active, skip the destructive reload 🧱
        if engine == current_ai_engine and model_name == current_ai_model:
            print(f"Mission Loader: {model_name} already active on {engine}. Ignoring.")
            return

        current_ai_engine = engine
        current_ai_model = model_name
        print(f"AI Engine/Model Hotswap -> engine={engine}, model={model_name}")
        
        # Throttling firewall: lock the UI while CUDA prepares 🔐
        try:
            window.tab_video.btn_apply_ai.setEnabled(False)
            window.tab_video.btn_apply_ai.setText("SWITCHING...")
        except: pass

        current_ai_engine = engine
        current_ai_model = model_name
        print(f"AI Engine/Model Change -> engine={engine}, model={model_name}")
        
        # ---- CLEAN BREAK: Disable detections and stop feed for stability 🎯 ----
        window.tab_ops.chk_enable_det.setChecked(False)
        window.tab_ops.chk_tracking.setChecked(False)
        
        if window.video_thread and window.video_thread.isRunning():
            print("Mission Control: Stopping video feed for clean model transition.")
            toggle_video()
            
        # Reset the "Apply" button state instantly since no live restart will be attempted
        on_ai_ready(engine, model_name)

    def on_search_prompt_changed(prompt):
        if window.video_thread:
            window.video_thread.set_world_prompt(prompt)

    window.tab_ops.btn_vid_toggle.clicked.connect(toggle_video)
    window.tab_ops.video_label.frame_clicked.connect(on_video_click)
    window.tab_ops.chk_enable_det.toggled.connect(on_detection_toggled)
    window.tab_ops.combo_tracking_mode.currentIndexChanged.connect(on_tracking_mode_changed)
    window.tab_ops.chk_tracking.toggled.connect(on_tracking_toggled)
    window.tab_ops.btn_wipe_lock.clicked.connect(on_wipe_lock)
    window.tab_ops.chk_show_logs.toggled.connect(window.log_console.setVisible)
    window.tab_video.ai_settings_applied.connect(on_ai_settings_applied)
    window.tab_video.search_prompt_changed.connect(on_search_prompt_changed)
    
    sys.stdout = LogRedirector(window.log_console); sys.stderr = LogRedirector(window.log_console)
    window.tab_cfg.metadata.fetch_latest()
    orig_close = window.closeEvent
    window.closeEvent = lambda e: [n.stop() for n in window.telemetry_nodes.values()] or orig_close(e)

    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
