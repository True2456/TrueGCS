import sys
import os
import subprocess
import time
from PySide6.QtWidgets import QApplication
from ui.main_window import GCSMainWindow
from video.video_thread import VideoThread
from telemetry.mavlink_thread import TelemetryThread
from PySide6.QtCore import QTimer

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
    """Attempts to find the gst-launch-1.0.exe binary in common Windows paths."""
    common_paths = [
        r"C:\gstreamer\1.0\msvc_x86_64\bin\gst-launch-1.0.exe",
        r"C:\gstreamer\1.0\x86_64\bin\gst-launch-1.0.exe",
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), r"gstreamer\1.0\msvc_x86_64\bin\gst-launch-1.0.exe")
    ]
    for p in common_paths:
        if os.path.exists(p): return p
    return "gst-launch-1.0.exe" # Fallback to PATH

def main():
    # Phase 24: GStreamer DLL Environmental Patch
    if sys.platform == "win32":
        base_gst = r"C:\ProgramData\Mission Planner\gstreamer\1.0\x86_64"
        dll_path = os.path.join(base_gst, "bin")
        plugin_path = os.path.join(base_gst, "lib", "gstreamer-1.0")
        
        if os.path.exists(dll_path):
            try:
                if sys.version_info >= (3, 8):
                    os.add_dll_directory(dll_path)
                os.environ["GST_PLUGIN_PATH"] = plugin_path
                # Also append to PATH as a fallback for the C/C++ backend
                os.environ["PATH"] = dll_path + os.pathsep + os.environ.get("PATH", "")
                
                print(f"Mission: GStreamer DLLs Ingested from Mission Planner Path.")
            except Exception as e:
                print(f"Mission: Failed to add DLL directory: {e}")
                
    # Global Zombie Assassin - Clears port 5010 of any crashed pipelines!
    if sys.platform == "win32":
        os.system("taskkill /F /IM gst-launch-1.0.exe >nul 2>&1")

    app = QApplication(sys.argv)
    window = GCSMainWindow()

    # Initialize global AI state for the mission 🚀
    global current_ai_engine, current_ai_model
    current_ai_engine = "CPU"
    current_ai_model = "YOLOv8n"

    # Initialize thread references
    window.video_thread = None
    window.tab_ops.video_label.video_thread = None
    window.relay_process = None
    
    # Connect connect button
    # 1.6 Connection & Telemetry Management
    def connect_telemetry_signals(win, tel):
        """Connects a new telemetry thread instance to the GCS UI."""
        tel.signals.heartbeat_received.connect(win.on_heartbeat)
        tel.signals.position_updated.connect(win.tab_ops.update_position)
        tel.signals.attitude_updated.connect(win.tab_ops.update_attitude)
        tel.signals.hud_updated.connect(lambda s, b, a, m: win.tab_ops.map_hud.update_telemetry(
            speed=s if s > -1 else None, batt=b if b > -1 else None, 
            alt=a if a > -1 else None, mode=m))
        tel.signals.status_text_updated.connect(lambda txt: win.lbl_status.setText(f"Drone: {txt}"))
        tel.signals.parameter_updated.connect(win.tab_cfg.update_param_value)
        tel.signals.parameters_loaded.connect(win.on_params_loaded)
        tel.signals.parameter_progress.connect(win.tab_cfg.update_param_progress)
        tel.signals.modes_available.connect(win.populate_flight_modes)
        win.tab_ops.map_widget.waypoint_requested.connect(tel.set_waypoint)
        win.tab_cfg.write_param_requested.connect(tel.set_parameter)
        win.tab_cfg.fetch_params_requested.connect(tel.fetch_parameters)
        win.tab_cfg.fetch_full_list_requested.connect(tel.request_all_params_list)
        win.pid_controller.gimbal_setpoint.connect(lambda p, y: tel.mount_control(int(p * 100), 0, int(y * 100)))

    def attempt_connection():
        # Force cleanup of any existing thread to recover COM port
        if window.telemetry:
            print("Dashboard: Recovery in progress... closing previous session.")
            window.telemetry.stop()
            window.telemetry = None
            time.sleep(0.5) # Driver cooldown for Windows serial stability

        if window.btn_connect.text() == "Disconnect":
            window.btn_connect.setText("Connect")
            window.lbl_status.setText("MAVLink: Disconnected")
            window.lbl_status.setStyleSheet("color: red; font-size: 14px;")
            return

        try:
            ctype, device = window.combo_type.currentData()
            baud_rate = 115200
            try: baud_rate = int(window.txt_p1.text())
            except: pass

            if ctype == "serial":
                window.telemetry = TelemetryThread(connection_string=device, baud=baud_rate)
            elif ctype == "udp":
                port = window.txt_p1.text()
                window.telemetry = TelemetryThread(connection_string=f"udpin:0.0.0.0:{port}")
            else:
                ip = window.txt_p1.text(); port = window.txt_p2.text()
                window.telemetry = TelemetryThread(connection_string=f"{ctype}:{ip}:{port}")

            connect_telemetry_signals(window, window.telemetry)
            
            # Start MAVLink Engine
            window.telemetry.start()
            window.lbl_status.setText("MAVLink: Connecting...")
            window.lbl_status.setStyleSheet("color: yellow; font-size: 14px;")
            window.btn_connect.setText("Disconnect")
            
            # Auto-fetch curated params after connection is confirmed
            QTimer.singleShot(3000, window.tab_cfg.request_curated_params)
        except Exception as e:
            window.lbl_status.setText("MAVLink: Connection Failed")
            window.lbl_status.setStyleSheet("color: red; font-size: 14px;")
            window.btn_connect.setText("Connect")
            print(f"Connection error: {e}")

    def toggle_video():
        if window.tab_ops.btn_vid_toggle.text() == "Start Video":
            if window.video_thread:
                window.video_thread.stop()
                # PySide6 C++ Protection: Prevent GC from annihilating hung QThreads mid-execution!
                if not hasattr(window, 'old_threads'): window.old_threads = []
                window.old_threads.append(window.video_thread)
            
            vtype = window.tab_ops.combo_vid_type.currentText()
            vport = window.tab_ops.txt_vid_port.text().strip()
            if not vport: vport = "5008"
            
            host = window.tab_ops.txt_vid_ip.text().strip()
            if not host: host = "0.0.0.0"
            
            gst_path = find_gstreamer()
            
            protocol = "udp" if "UDP" in vtype else "rtp"
            
            if "USB" in vtype:
                try: src = int(vport)
                except: src = 0
            else:
                src = f"{protocol}://{host}:{vport}"
            
            # Initialize VideoThread and start it before applying AI config
            window.video_thread = VideoThread(stream_url=src)
            window.video_thread.relay_mp = False
            window.video_thread.gst_path = gst_path
            # Connect UI components to the thread
            window.tab_ops.video_label.video_thread = window.video_thread
            window.video_thread.frame_ready.connect(window.update_video_frame)
            window.video_thread.tracking_error.connect(window.pid_controller.calculate_adjustment)
            window.video_thread.target_status.connect(window.tab_ops.update_target_status)
            # Start the thread
            window.video_thread.start()
            # Apply AI configuration after thread is running
            window.video_thread.set_ai_config(current_ai_engine, current_ai_model)
            window.tab_ops.btn_vid_toggle.setText("Stop Video")

        else:
            if window.video_thread:
                window.video_thread.stop()
            pass # relay_process is now handled entirely inside video_thread 
            window.tab_ops.btn_vid_toggle.setText("Start Video")
            window.tab_ops.video_label.clear()

    def toggle_tracking(checked):
        if not checked and window.video_thread:
            window.video_thread.set_tracking_point(None, None)

    def update_vision_state(enabled):
        if window.video_thread:
            window.video_thread.set_show_detections(enabled)

    # Connect UI signals
    window.tab_ops.btn_vid_toggle.clicked.connect(toggle_video)
    # Minimalist Signal Mapping
    
    # Global AI Engine State
    current_ai_engine = "CPU"
    current_ai_model = "RT-DETR"
    
    def handle_ai_config(engine, model):
        global current_ai_engine, current_ai_model
        current_ai_engine = engine
        current_ai_model = model
        print(f"Main: Atomic AI Mission Sync -> {model} on {engine}")
        if window.video_thread:
            window.video_thread.set_ai_config(engine, model)
    
    def handle_search_prompt(prompt):
        if window.video_thread:
            window.video_thread.set_world_prompt(prompt)
    
    window.tab_video.ai_settings_applied.connect(handle_ai_config)
    window.tab_video.search_prompt_changed.connect(handle_search_prompt)
    
    # Detection checkbox toggles model loading/unloading
    window.tab_ops.chk_enable_det.toggled.connect(lambda state: window.video_thread.set_ai_config(current_ai_engine, "RT-DETR" if state else "None"))
    # Tracking checkbox toggles bounding‑box visibility
    window.tab_ops.chk_tracking.toggled.connect(lambda state: window.video_thread.set_show_detections(state))
    
    window.tab_ops.chk_show_logs.toggled.connect(window.log_console.setVisible)
    
    window.tab_ops.chk_tracking.toggled.connect(toggle_tracking)
    window.tab_ops.chk_enable_det.toggled.connect(update_vision_state)
    window.tab_ops.btn_wipe_lock.clicked.connect(lambda: window.video_thread.set_tracking_point(None, None) if window.video_thread else None)
    
    window.btn_connect.clicked.connect(attempt_connection)
    
    # Log Console Connection
    window.tab_ops.chk_show_logs.toggled.connect(window.log_console.setVisible)
    
    # Redirect standard output to our tactical console
    sys.stdout = LogRedirector(window.log_console)
    sys.stderr = LogRedirector(window.log_console)
    print("Dashboard: Mission Debug Console Active.")

    # Start Param Metadata Sync (Professionally fetches bitmasks/enums from ArduPilot)
    print("Initializing ArduPilot Parameter Metadata Sync...")
    window.tab_cfg.metadata.fetch_latest()

    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
