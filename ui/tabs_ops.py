import os
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout, QLabel, QComboBox, QPushButton, QCheckBox, QLineEdit, QSplitter, QSizePolicy
from PySide6.QtCore import Qt, Signal

from ui.map_widget import SatelliteMapWidget
from ui.hud_overlay import MapHUD, VideoHUD


class ClickableVideoLabel(QLabel):
    frame_clicked = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.video_thread = None
        self.chk_tracking = None
        self._frame_w = 0
        self._frame_h = 0

    def set_source_frame_size(self, width, height):
        self._frame_w = int(width)
        self._frame_h = int(height)

    def mousePressEvent(self, event):
        pm = self.pixmap()
        if not pm or pm.isNull() or self._frame_w <= 0 or self._frame_h <= 0:
            return

        label_w = self.width()
        label_h = self.height()
        pm_w = pm.width()
        pm_h = pm.height()
        if pm_w <= 0 or pm_h <= 0:
            return

        off_x = (label_w - pm_w) / 2.0
        off_y = (label_h - pm_h) / 2.0
        click_x = float(event.position().x()) - off_x
        click_y = float(event.position().y()) - off_y
        if click_x < 0 or click_y < 0 or click_x > pm_w or click_y > pm_h:
            return

        src_x = int((click_x / pm_w) * self._frame_w)
        src_y = int((click_y / pm_h) * self._frame_h)
        src_x = max(0, min(self._frame_w - 1, src_x))
        src_y = max(0, min(self._frame_h - 1, src_y))
        self.frame_clicked.emit(src_x, src_y)


class OpsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.map_widget = None
        self.map_hud = None
        self.video_hud = None
        self._last_yaw = 0.0
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # Left Panel (Video & Flight Controls)
        left_widget = QWidget()
        left_pnl = QVBoxLayout(left_widget)
        left_pnl.setContentsMargins(0, 0, 5, 0)
        
        # Video Section
        vid_box = QGroupBox("Target Recon / Video")
        vid_layout = QVBoxLayout(vid_box)
        vid_layout.setContentsMargins(5, 15, 5, 5)

        vid_ctrl_layout1 = QHBoxLayout()
        vid_ctrl_layout2 = QHBoxLayout()
        
        # Row 1: Connection Settings
        vid_ctrl_layout1.addWidget(QLabel("TYPE:"))
        self.combo_vid_type = QComboBox()
        self.combo_vid_type.addItems(["UDP Stream", "USB Sensor", "RTP Stream", "RTMP Server (DJI)"])
        self.combo_vid_type.setFixedWidth(120)
        self.combo_vid_type.currentIndexChanged.connect(self._on_vid_type_changed)
        vid_ctrl_layout1.addWidget(self.combo_vid_type)
        
        vid_ctrl_layout1.addWidget(QLabel("IP:"))
        self.txt_vid_ip = QLineEdit("0.0.0.0")
        self.txt_vid_ip.setStyleSheet("background-color: #111a22; color: #00ddff; padding: 2px;")
        self.txt_vid_ip.setMaximumWidth(90)
        vid_ctrl_layout1.addWidget(self.txt_vid_ip)
        
        vid_ctrl_layout1.addWidget(QLabel("PORT:"))
        self.txt_vid_port = QLineEdit("5008")
        self.txt_vid_port.setStyleSheet("background-color: #111a22; color: #00ddff; padding: 2px;")
        self.txt_vid_port.setMaximumWidth(50)
        vid_ctrl_layout1.addWidget(self.txt_vid_port)
        vid_ctrl_layout1.addStretch()
        
        # Row 2: Operation Toggles
        self.btn_vid_toggle = QPushButton("Start Video")
        self.btn_vid_toggle.setFixedWidth(100)
        vid_ctrl_layout2.addWidget(self.btn_vid_toggle)
        
        self.chk_enable_det = QCheckBox("Detect")
        self.chk_enable_det.setChecked(False)
        self.chk_tracking = QCheckBox("Track")
        self.chk_tracking.setChecked(False)
        self.combo_tracking_mode = QComboBox()
        self.combo_tracking_mode.addItem("No Tracking", userData="none")
        self.combo_tracking_mode.addItem("Click Nearest Detection", userData="nearest")
        self.combo_tracking_mode.addItem("Click Pixel Seed", userData="seed")
        self.combo_tracking_mode.addItem("Click Center Slew", userData="center")
        self.chk_show_logs = QCheckBox("Logs")
        self.chk_show_logs.setChecked(False)
        vid_ctrl_layout2.addWidget(self.chk_enable_det)
        vid_ctrl_layout2.addWidget(self.chk_tracking)
        vid_ctrl_layout2.addWidget(self.combo_tracking_mode)
        vid_ctrl_layout2.addWidget(self.chk_show_logs)
        vid_ctrl_layout2.addStretch()
        
        vid_layout.addLayout(vid_ctrl_layout1)
        vid_layout.addLayout(vid_ctrl_layout2)
        
        # Row 3: RTMP/Stream URL Display (Contextual HUD)
        self.lbl_stream_url = QLabel("")
        self.lbl_stream_url.setStyleSheet("color: #00ddff; font-family: 'Consolas'; font-size: 10px; background: rgba(0,0,0,0.2); padding: 2px;")
        self.lbl_stream_url.setAlignment(Qt.AlignCenter)
        self.lbl_stream_url.setVisible(False)
        vid_layout.addWidget(self.lbl_stream_url)

        # Video Display with Overlay
        vid_container = QWidget()
        vid_stack = QGridLayout(vid_container)
        vid_stack.setContentsMargins(0, 0, 0, 0)

        self.video_label = ClickableVideoLabel()
        # Click‑to‑track removed; tracking point is now controlled via the Tracking checkbox
        self.video_label.setMinimumSize(100, 100)
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_label.setStyleSheet("background-color: #000; border: 1px solid #2a4555;")
        self.video_label.setAlignment(Qt.AlignCenter)
        
        self.video_hud = VideoHUD()
        
        vid_stack.addWidget(self.video_label, 0, 0)
        vid_stack.addWidget(self.video_hud, 0, 0)
        
        vid_layout.addWidget(vid_container)
        
        left_pnl.addWidget(vid_box)
        left_pnl.setStretch(0, 10) # 10:1 stretch for the video panel
        
        # Bottom row: Compact Telemetry data (Side-by-side)
        telem_row = QHBoxLayout()
        telem_row.setContentsMargins(0, 5, 0, 0)
        telem_row.setSpacing(5)

        # Attitude HUD Component
        att_box = QGroupBox("Attitude")
        att_layout = QGridLayout(att_box)
        att_layout.setContentsMargins(8, 12, 8, 8)
        att_layout.setSpacing(2)
        self.lbl_roll = QLabel("0.0°"); self.lbl_roll.setObjectName("DataLabel")
        self.lbl_pitch = QLabel("0.0°"); self.lbl_pitch.setObjectName("DataLabel")
        self.lbl_yaw = QLabel("0.0°"); self.lbl_yaw.setObjectName("DataLabel")
        
        att_layout.addWidget(QLabel("R:"), 0, 0); att_layout.addWidget(self.lbl_roll, 0, 1)
        att_layout.addWidget(QLabel("P:"), 0, 2); att_layout.addWidget(self.lbl_pitch, 0, 3)
        att_layout.addWidget(QLabel("Y:"), 1, 0); att_layout.addWidget(self.lbl_yaw, 1, 1)
        telem_row.addWidget(att_box)
        
        # Target HUD Component
        tgt_box = QGroupBox("Tactical Target")
        tgt_layout = QGridLayout(tgt_box)
        tgt_layout.setContentsMargins(8, 12, 8, 8)
        tgt_layout.setSpacing(2)
        self.lbl_tgt_status = QLabel("SEARCHING"); self.lbl_tgt_status.setObjectName("DataLabel")
        self.lbl_tgt_offset = QLabel("0, 0 px"); self.lbl_tgt_offset.setObjectName("DataLabel")
        self.lbl_tgt_conf = QLabel("0%"); self.lbl_tgt_conf.setObjectName("DataLabel")
        
        tgt_layout.addWidget(QLabel("ST:"), 0, 0); tgt_layout.addWidget(self.lbl_tgt_status, 0, 1)
        tgt_layout.addWidget(QLabel("OFF:"), 0, 2); tgt_layout.addWidget(self.lbl_tgt_offset, 0, 3)
        tgt_layout.addWidget(QLabel("CF:"), 1, 0); tgt_layout.addWidget(self.lbl_tgt_conf, 1, 1)
        
        self.btn_wipe_lock = QPushButton("Wipe")
        self.btn_wipe_lock.setFixedWidth(50)
        self.btn_wipe_lock.setStyleSheet("background-color: rgba(255, 50, 50, 0.1); border-color: #ff3232; color: #ff3232; font-size: 9px;")
        tgt_layout.addWidget(self.btn_wipe_lock, 1, 2, 1, 2)
        
        telem_row.addWidget(tgt_box)
        left_pnl.addLayout(telem_row)
        
        splitter.addWidget(left_widget)

        # Right Panel (Map Background with HUD Overlay)
        map_container = QWidget()
        map_grid = QGridLayout(map_container)
        map_grid.setContentsMargins(5, 0, 0, 0)
        
        self.map_widget = SatelliteMapWidget()
        self.map_hud = MapHUD()
        
        map_grid.addWidget(self.map_widget, 0, 0)
        map_grid.addWidget(self.map_hud, 0, 0) # Overlay on same cell
        
        splitter.addWidget(map_container)
        
        # Force Layout 1/3 (Video) and 2/3 (Satellite)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    def update_position(self, lat, lon, alt):
        """Called by telemetry signal: position_updated(node_id, sysid, lat, lon, alt)."""
        if self.map_hud:
            self.map_hud.update_telemetry(lat=lat, lon=lon, alt=alt)

    def update_attitude(self, roll, pitch, yaw):
        """Called by telemetry signal: attitude_updated(float, float, float)."""
        self.lbl_roll.setText(f"{roll:.1f}°")
        self.lbl_pitch.setText(f"{pitch:.1f}°")
        self.lbl_yaw.setText(f"{yaw:.1f}°")
        self._last_yaw = yaw
        if self.video_hud:
            self.video_hud.update_attitude(roll, pitch)

    def _toggle_pilot_hud(self, checked):
        if self.video_hud:
            self.video_hud.setVisible(checked)

    def _on_vid_type_changed(self, index):
        type_str = self.combo_vid_type.currentText()
        if "RTMP" in type_str:
            import socket
            try:
                # Determine local IP for drone connection
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
            except:
                local_ip = "127.0.0.1"
                
            url = f"rtmp://{local_ip}:1935/live/drone"
            self.lbl_stream_url.setText(f"POINT DJI DRONE TO: {url}")
            self.lbl_stream_url.setVisible(True)
            # Default RTMP port for DJI
            self.txt_vid_port.setText("1935")
            self.txt_vid_ip.setText(local_ip)
        else:
            self.lbl_stream_url.setVisible(False)
            if "UDP" in type_str:
                self.txt_vid_port.setText("5008")
                self.txt_vid_ip.setText("0.0.0.0")

    def update_target_status(self, status, off_x, off_y, conf):
        self.lbl_tgt_status.setText(status)
        self.lbl_tgt_offset.setText(f"{off_x}, {off_y} px")
        self.lbl_tgt_conf.setText(f"{int(conf*100)}%")
        
        if status == "LOCKED":
            self.lbl_tgt_status.setStyleSheet("color: #00ff78; font-weight: bold;")
        elif status == "LOST":
            self.lbl_tgt_status.setStyleSheet("color: #ffaa00; font-weight: bold;")
        else:
            self.lbl_tgt_status.setStyleSheet("color: #92b0c3;")
