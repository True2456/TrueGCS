import os
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout, QLabel, QComboBox, QPushButton, QCheckBox, QLineEdit, QSplitter, QSizePolicy, QSlider
from PySide6.QtCore import Qt, Signal

from ui.map_widget import SatelliteMapWidget
from ui.hud_overlay import MapHUD, VideoHUD, SensorPanel


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
    class_filter_changed = Signal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.map_widget = None
        self.map_hud = None
        self.sensor_panel = None
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
        self.combo_vid_type.addItems(["UDP Stream", "USB Sensor"])
        self.combo_vid_type.setFixedWidth(140)
        self.combo_vid_type.currentIndexChanged.connect(self._on_vid_type_changed)
        vid_ctrl_layout1.addWidget(self.combo_vid_type)
        
        self.lbl_vid_ip = QLabel("IP:")
        vid_ctrl_layout1.addWidget(self.lbl_vid_ip)
        self.txt_vid_ip = QLineEdit("0.0.0.0")
        self.txt_vid_ip.setStyleSheet("background-color: #111a22; color: #00ddff; padding: 2px;")
        self.txt_vid_ip.setMaximumWidth(90)
        vid_ctrl_layout1.addWidget(self.txt_vid_ip)
        
        self.lbl_vid_port = QLabel("PORT:")
        vid_ctrl_layout1.addWidget(self.lbl_vid_port)
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
        
        # Navigation Toggles 🛰️ (Independent Dual-GPS Sim)
        self.chk_gps_enabled = QCheckBox("GPS") 
        self.chk_gps_enabled.setChecked(True)
        self.chk_gps2_enabled = QCheckBox("GPS2 / TRN")
        self.chk_gps2_enabled.setChecked(True)
        
        self.combo_tracking_mode = QComboBox()
        self.combo_tracking_mode.addItem("No Tracking", userData="none")
        self.combo_tracking_mode.addItem("Click Nearest Detection", userData="nearest")
        self.combo_tracking_mode.addItem("Click Pixel Seed", userData="seed")
        self.combo_tracking_mode.addItem("Click Center Slew", userData="center")
        self.chk_show_logs = QCheckBox("Logs")
        self.chk_show_logs.setChecked(False)
        
        vid_ctrl_layout2.addWidget(self.chk_enable_det)
        vid_ctrl_layout2.addWidget(self.chk_tracking)
        vid_ctrl_layout2.addWidget(self.chk_gps_enabled)
        vid_ctrl_layout2.addWidget(self.chk_gps2_enabled)
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
        # BREAK THE FEEDBACK LOOP: Set Ignored policy so the pixmap size doesn't force the layout to grow 🛡️
        self.video_label.setMinimumSize(400, 300) # ENSURE VISIBILITY: Prevent layout from collapsing the label to 1x1 🛡️
        self.video_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.video_label.setStyleSheet("background-color: #000; border: 1px solid #2a4555;")
        self.video_label.setAlignment(Qt.AlignCenter)
        
        self.video_hud = VideoHUD()
        
        vid_stack.addWidget(self.video_label, 0, 0)
        vid_stack.addWidget(self.video_hud, 0, 0)
        
        vid_layout.addWidget(vid_container)

        self.btn_show_targets = QPushButton("Show Tactical Target Groups")
        self.btn_show_targets.setCheckable(True)
        self.btn_show_targets.setObjectName("TacticalButton")
        self.btn_show_targets.setStyleSheet("QPushButton:checked { background-color: rgba(0, 221, 255, 0.1); color: #00ddff; border-color: #00ddff; }")
        vid_layout.addWidget(self.btn_show_targets)

        # 1.5. Collapsible Mission Class Filter Section 🚀
        self.class_box = QGroupBox("Mission Class Filter")
        self.class_lay = QVBoxLayout(self.class_box)
        self.class_grid_container = QWidget()
        self.class_grid = QGridLayout(self.class_grid_container)
        self.class_lay.addWidget(self.class_grid_container)
        self.class_box.setVisible(False)
        vid_layout.addWidget(self.class_box)
        
        self.btn_show_targets.toggled.connect(self.class_box.setVisible)
        # Initialize with default RT-DETR groups 🚀
        self.refresh_class_filters("RT-DETR")
        
        left_pnl.addWidget(vid_box)
        left_pnl.setStretch(0, 10) # 10:1 stretch for the video panel
        
        # Bottom row: Compact Telemetry data (Side-by-side)
        telem_row = QHBoxLayout()
        telem_row.setContentsMargins(0, 5, 0, 0)
        telem_row.setSpacing(5)

        # Attitude HUD Component
        att_box = QGroupBox("Attitude")
        att_box.setFixedWidth(140) # COMPACTED: Prevent pushing layout in splitter 🛰️
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
        tgt_box.setFixedWidth(200) # COMPACTED: Prevent pushing layout in splitter 🛰️
        tgt_layout = QGridLayout(tgt_box)
        tgt_layout.setContentsMargins(8, 12, 8, 8)
        tgt_layout.setSpacing(2)
        self.lbl_tgt_status = QLabel("SEARCHING"); self.lbl_tgt_status.setObjectName("DataLabel")
        self.lbl_tgt_offset = QLabel("0, 0 px"); self.lbl_tgt_offset.setObjectName("DataLabel")
        self.lbl_tgt_conf = QLabel("0%"); self.lbl_tgt_conf.setObjectName("DataLabel")
        
        tgt_layout.addWidget(QLabel("ST:"), 0, 0); tgt_layout.addWidget(self.lbl_tgt_status, 0, 1)
        tgt_layout.addWidget(QLabel("OFF:"), 0, 2); tgt_layout.addWidget(self.lbl_tgt_offset, 0, 3)
        tgt_layout.addWidget(QLabel("CF:"), 1, 0); tgt_layout.addWidget(self.lbl_tgt_conf, 1, 1)
        
        # Tactical Confidence Slider 🎯
        conf_box = QHBoxLayout()
        self.slider_conf = QSlider(Qt.Horizontal)
        self.slider_conf.setRange(0, 100)
        self.slider_conf.setValue(25)
        self.slider_conf.setToolTip("Tactical Confidence Threshold")
        self.slider_conf.setStyleSheet("""
            QSlider::handle:horizontal {
                background: #00ddff;
                width: 10px;
                border-radius: 5px;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #111a22;
                border: 1px solid #335566;
            }
        """)
        conf_box.addWidget(self.slider_conf)
        tgt_layout.addLayout(conf_box, 1, 2, 1, 2)

        self.btn_wipe_lock = QPushButton("Wipe")
        self.btn_wipe_lock.setFixedWidth(50)
        self.btn_wipe_lock.setStyleSheet("background-color: rgba(255, 50, 50, 0.1); border-color: #ff3232; color: #ff3232; font-size: 9px;")
        tgt_layout.addWidget(self.btn_wipe_lock, 2, 0, 1, 4)
        
        telem_row.addWidget(tgt_box)
        left_pnl.addLayout(telem_row)
        
        splitter.addWidget(left_widget)

        # Right Panel (Map Background with HUD Overlay)
        map_container = QWidget()
        map_grid = QGridLayout(map_container)
        map_grid.setContentsMargins(5, 0, 0, 0)
        
        self.map_widget = SatelliteMapWidget()
        self.map_hud = MapHUD()
        self.sensor_panel = SensorPanel()
        self.sensor_panel.setVisible(False)
        
        map_grid.addWidget(self.map_widget, 0, 0)
        map_grid.addWidget(self.map_hud, 0, 0)
        
        # Sensor Panel Alignment (Right Side)
        map_grid.addWidget(self.sensor_panel, 0, 0, Qt.AlignRight | Qt.AlignTop)
        
        # Sensor Toggle Button (Floating on Map)
        self.btn_toggle_sensors = QPushButton("SENSORS")
        self.btn_toggle_sensors.setCheckable(True)
        self.btn_toggle_sensors.setFixedSize(70, 24)
        self.btn_toggle_sensors.setStyleSheet("""
            QPushButton {
                background-color: rgba(9, 14, 17, 0.8);
                color: #92b0c3;
                border: 1px solid rgba(0, 221, 255, 0.3);
                font-size: 9px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:checked {
                background-color: #00ddff;
                color: #090e11;
                border: 1px solid #00ddff;
            }
        """)
        self.btn_toggle_sensors.toggled.connect(self.sensor_panel.setVisible)
        map_grid.addWidget(self.btn_toggle_sensors, 0, 0, Qt.AlignRight | Qt.AlignBottom)
        
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
        self.lbl_stream_url.setVisible(False)
        if "USB" in type_str:
            self.txt_vid_port.setText("0")
            self.lbl_vid_ip.setVisible(False)
            self.txt_vid_ip.setVisible(False)
            self.lbl_vid_port.setText("INDEX:")
        else:
            self.lbl_vid_ip.setVisible(True)
            self.txt_vid_ip.setVisible(True)
            self.lbl_vid_port.setText("PORT:")
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

    def refresh_class_filters(self, model_type):
        """Build the tactical filter grid based on the active mission model 🚀"""
        # Clear existing checkboxes
        for i in reversed(range(self.class_grid.count())): 
            self.class_grid.itemAt(i).widget().setParent(None)
            
        mt = (model_type or "").upper()
        self.checkboxes = []
        
        if "VISDRONE" in mt or "YOLO26" in mt:
            self.class_box.setTitle("Recon Targets: VisDrone (10 Classes)")
            names = ["Pedestrian", "People", "Bicycle", "Car", "Van", "Truck", "Tricycle", "Awning-Tricycle", "Bus", "Motor"]
            for i, name in enumerate(names):
                cb = QCheckBox(name)
                cb.setChecked(True)
                cb.setProperty("ids", [i])
                cb.stateChanged.connect(self._emit_class_filter)
                self.class_grid.addWidget(cb, i // 3, i % 3)
                self.checkboxes.append(cb)
        else:
            self.class_box.setTitle("Recon Targets: RT-DETR (8 Groups)")
            groups = [
                ("Humanoid", [0]),
                ("Two-Wheelers", [1, 3]),
                ("Standard Vehicles", [2, 7]),
                ("Aviation/Marine", [4, 8]),
                ("Nature/Animals", list(range(14, 24))),
                ("Socio-Furniture", list(range(56, 62))),
                ("Electronics", list(range(62, 68))),
                ("Household Items", list(range(68, 80)))
            ]
            for i, (name, ids) in enumerate(groups):
                cb = QCheckBox(name)
                cb.setChecked(True)
                cb.setProperty("ids", ids)
                cb.stateChanged.connect(self._emit_class_filter)
                self.class_grid.addWidget(cb, i // 3, i % 3)
                self.checkboxes.append(cb)
        
        self._emit_class_filter()

    def _emit_class_filter(self):
        active_ids = []
        for cb in self.checkboxes:
            if cb.isChecked():
                active_ids.extend(cb.property("ids"))
        self.class_filter_changed.emit(active_ids)
