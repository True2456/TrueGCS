import os
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout, QLabel, QComboBox, QPushButton, QCheckBox, QLineEdit, QSplitter, QSizePolicy
from PySide6.QtCore import Qt

from ui.map_widget import SatelliteMapWidget
from ui.hud_overlay import MapHUD, VideoHUD


class ClickableVideoLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.video_thread = None
        self.chk_tracking = None

    def mousePressEvent(self, event):
        # Click-to-track removed; clicks are ignored.
        pass


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
        self.combo_vid_type.addItems(["UDP Stream", "USB Sensor", "RTP Stream"])
        self.combo_vid_type.setFixedWidth(100)
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
        self.chk_show_logs = QCheckBox("Logs")
        self.chk_show_logs.setChecked(False)
        vid_ctrl_layout2.addWidget(self.chk_enable_det)
        vid_ctrl_layout2.addWidget(self.chk_tracking)
        vid_ctrl_layout2.addWidget(self.chk_show_logs)
        vid_ctrl_layout2.addStretch()
        
        vid_layout.addLayout(vid_ctrl_layout1)
        vid_layout.addLayout(vid_ctrl_layout2)

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
        
        # Attitude HUD Component
        att_box = QGroupBox("Attitude HUD")
        att_layout = QGridLayout(att_box)
        self.lbl_roll = QLabel("0.0°"); self.lbl_roll.setObjectName("DataLabel")
        self.lbl_pitch = QLabel("0.0°"); self.lbl_pitch.setObjectName("DataLabel")
        self.lbl_yaw = QLabel("0.0°"); self.lbl_yaw.setObjectName("DataLabel")
        
        att_layout.addWidget(QLabel("ROLL:"), 0, 0); att_layout.addWidget(self.lbl_roll, 0, 1)
        att_layout.addWidget(QLabel("PITCH:"), 1, 0); att_layout.addWidget(self.lbl_pitch, 1, 1)
        att_layout.addWidget(QLabel("YAW:"), 2, 0); att_layout.addWidget(self.lbl_yaw, 2, 1)
        left_pnl.addWidget(att_box)
        
        # Target HUD Component
        tgt_box = QGroupBox("Tactical Target Data")
        tgt_layout = QGridLayout(tgt_box)
        self.lbl_tgt_status = QLabel("SEARCHING"); self.lbl_tgt_status.setObjectName("DataLabel")
        self.lbl_tgt_offset = QLabel("0, 0 px"); self.lbl_tgt_offset.setObjectName("DataLabel")
        self.lbl_tgt_conf = QLabel("0%"); self.lbl_tgt_conf.setObjectName("DataLabel")
        
        tgt_layout.addWidget(QLabel("STATUS:"), 0, 0); tgt_layout.addWidget(self.lbl_tgt_status, 0, 1)
        tgt_layout.addWidget(QLabel("OFFSET:"), 1, 0); tgt_layout.addWidget(self.lbl_tgt_offset, 1, 1)
        tgt_layout.addWidget(QLabel("CONF:"), 2, 0); tgt_layout.addWidget(self.lbl_tgt_conf, 2, 1)
        
        self.btn_wipe_lock = QPushButton("Wipe Lock")
        self.btn_wipe_lock.setStyleSheet("background-color: rgba(255, 50, 50, 0.1); border-color: #ff3232; color: #ff3232;")
        tgt_layout.addWidget(self.btn_wipe_lock, 3, 0, 1, 2)
        
        left_pnl.addWidget(tgt_box)
        
        left_pnl.addStretch()
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
        """Called by telemetry signal: position_updated(float, float, float)."""
        if self.map_hud:
            self.map_hud.update_telemetry(lat=lat, lon=lon, alt=alt)
        # Update drone marker on the satellite map
        self.map_widget.update_drone_position(lat, lon, heading=self._last_yaw)

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
