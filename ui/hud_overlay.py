from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea, QPushButton, QSizePolicy
from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QTransform

class HUDLabel(QFrame):
    """A premium, transparent HUD data block."""
    def __init__(self, label, unit="", parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(9, 14, 17, 0.85);
                border-left: 2px solid #00ddff;
                border-right: 1px solid rgba(0, 221, 255, 0.2);
                border-top: 1px solid rgba(0, 221, 255, 0.1);
                border-bottom: 1px solid rgba(0, 221, 255, 0.1);
                border-radius: 6px;
            }
        """)
        self.setFixedWidth(110) # Enforce a tight, consistent width for all HUD blocks
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(0)

        self.lbl_title = QLabel(label.upper())
        self.lbl_title.setStyleSheet("color: rgba(146, 176, 195, 0.7); font-size: 8px; font-weight: bold; letter-spacing: 1px;")
        
        self.lbl_value = QLabel("---")
        self.lbl_value.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold; font-family: 'Consolas';")
        
        self.lbl_unit = QLabel(unit)
        self.lbl_unit.setStyleSheet("color: #00ddff; font-size: 9px;")

        h_lay = QHBoxLayout()
        h_lay.setSpacing(4)
        h_lay.addWidget(self.lbl_value)
        h_lay.addWidget(self.lbl_unit)
        h_lay.addStretch()

        layout.addWidget(self.lbl_title)
        layout.addLayout(h_lay)

    def set_value(self, value):
        if self.lbl_value.text() == str(value):
            return # Prevent unnecessary redrawing/flickering
        self.lbl_value.setText(str(value))

class PFCHorizon(QWidget):
    """Battlefield-style Artificial Horizon (PFD) with Pitch & Roll support."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(300, 300)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.roll = 0.0
        self.pitch = 0.0
        self.setStyleSheet("background: transparent; border: none;")

    def update_attitude(self, roll, pitch):
        self.roll = roll
        self.pitch = pitch
        self.update() # Trigger paintEvent

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        cx = self.width() / 2
        cy = self.height() / 2
        
        # 1. Fixed Center Mark (White/Cyan)
        painter.setPen(QPen(QColor(0, 221, 255), 2))
        painter.setBrush(QColor(255, 255, 255))
        painter.drawRect(cx - 20, cy - 1, 40, 2)
        
        # 2. Dynamic Component (Roll + Pitch)
        painter.translate(cx, cy)
        painter.rotate(-self.roll) # Roll rotation
        painter.translate(0, self.pitch * 2) # Pitch elevation (2px per degree)

        # Draw Horizon Line
        painter.setPen(QPen(QColor(0, 221, 255, 100), 2))
        painter.drawLine(-100, 0, 100, 0)
        
        # Draw Pitch Ladder
        painter.setFont(QFont("Consolas", 8))
        for p in range(-30, 31, 10):
            if p == 0: continue
            y = -p * 2
            w = 50 if abs(p) % 20 == 0 else 30
            painter.setPen(QPen(QColor(0, 221, 255) if p > 0 else QColor(255, 50, 50), 1))
            painter.drawLine(-w//2, y, w//2, y)
            painter.drawText(w//2 + 5, y + 4, str(abs(p)))
            painter.drawText(-w//2 - 20, y + 4, str(abs(p)))

class MapHUD(QWidget):
    """Refined Map HUD — Mission Data at Bottom-Center, Mode at Top."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Top Row: Lat, Lon, Mode (Aligned Left)
        top_row = QHBoxLayout()
        self.hud_lat = HUDLabel("Latitude")
        self.hud_lon = HUDLabel("Longitude")
        self.hud_mode = HUDLabel("Mode")
        self.hud_mode.setMinimumWidth(90) # 25% Reduction Applied
        
        top_row.addWidget(self.hud_lat)
        top_row.addWidget(self.hud_lon)
        top_row.addWidget(self.hud_mode)
        top_row.addStretch() # Align to left
        layout.addLayout(top_row)
        
        layout.addStretch()
        
        # Bottom Row: Alt, Speed, Battery (Aligned Left, matching Top Row)
        bot_row = QHBoxLayout()
        self.hud_alt = HUDLabel("Altitude", "m")
        self.hud_speed = HUDLabel("Air Speed", "m/s")
        self.hud_batt = HUDLabel("Battery", "V")
        
        bot_row.addWidget(self.hud_alt)
        bot_row.addWidget(self.hud_speed)
        bot_row.addWidget(self.hud_batt)
        bot_row.addStretch() # Align to left
        layout.addLayout(bot_row)

    def update_telemetry(self, lat=None, lon=None, alt=None, speed=None, batt=None, mode=None):
        if lat is not None: self.hud_lat.set_value(f"{lat:.6f}")
        if lon is not None: self.hud_lon.set_value(f"{lon:.6f}")
        if alt is not None: self.hud_alt.set_value(f"{alt:.1f}")
        if speed is not None: self.hud_speed.set_value(f"{speed:.1f}")
        if batt is not None: self.hud_batt.set_value(f"{batt:.1f}")
        if mode is not None: self.hud_mode.set_value(mode)

class VideoHUD(QWidget):
    """Clean Pilot PFD for Video Feed."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.pfd = PFCHorizon(self)
        layout.addStretch()

    def resizeEvent(self, event):
        self.pfd.move((self.width() - self.pfd.width()) // 2, 
                      (self.height() - self.pfd.height()) // 2)

    def update_attitude(self, roll, pitch):
        self.pfd.update_attitude(roll, pitch)

class SensorDataBlock(QWidget):
    """A small, high-density data row for the sensor panel."""
    def __init__(self, label, value="---", color="#00ddff", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        
        lbl = QLabel(label.upper())
        lbl.setStyleSheet("color: rgba(146, 176, 195, 0.6); font-size: 8px; font-weight: bold;")
        
        self.val = QLabel(value)
        self.val.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold; font-family: 'Consolas';")
        self.val.setAlignment(Qt.AlignRight)
        
        layout.addWidget(lbl)
        layout.addStretch()
        layout.addWidget(self.val)

    def set_value(self, value, color=None):
        self.val.setText(str(value))
        if color:
            self.val.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold; font-family: 'Consolas';")

class DroneSensorCard(QFrame):
    """A collapsible card displaying telemetry and sensor data for a single drone in the swarm."""
    def __init__(self, node_id, sys_id, parent=None):
        super().__init__(parent)
        self.node_id = node_id
        self.sys_id = sys_id
        self.is_expanded = False
        
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(14, 22, 28, 0.9);
                border: 1px solid rgba(0, 221, 255, 0.2);
                border-radius: 6px;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(4)
        
        # --- HEADER (Clickable) ---
        self.btn_header = QPushButton(f"NODE {node_id}  |  SYSID {sys_id}")
        self.btn_header.setCursor(Qt.PointingHandCursor)
        self.btn_header.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #00ddff;
                font-size: 11px;
                font-weight: bold;
                text-align: left;
                border: none;
                padding: 2px;
            }
            QPushButton:hover { color: #ffffff; }
        """)
        self.btn_header.clicked.connect(self.toggle_expansion)
        
        # Basic Stats (Always Visible)
        basic_lay = QHBoxLayout()
        self.lbl_mode = QLabel("MODE: ---")
        self.lbl_alt = QLabel("ALT: 0.0m")
        self.lbl_batt = QLabel("BATT: 0.0V")
        for lbl in [self.lbl_mode, self.lbl_alt, self.lbl_batt]:
            lbl.setStyleSheet("color: #92b0c3; font-size: 9px; font-weight: bold; border: none; background: transparent;")
            basic_lay.addWidget(lbl)
        basic_lay.addStretch()
        
        main_layout.addWidget(self.btn_header)
        main_layout.addLayout(basic_lay)
        
        # --- EXPANDABLE BODY ---
        self.body_widget = QWidget()
        self.body_widget.setStyleSheet("border: none; background: transparent;")
        body_layout = QVBoxLayout(self.body_widget)
        body_layout.setContentsMargins(0, 8, 0, 0)
        body_layout.setSpacing(6)
        
        self.block_gps_stat = SensorDataBlock("GPS Status", "ACTIVE", "#00ff78")
        self.block_airspeed = SensorDataBlock("Airspeed")
        self.block_gps2_fix = SensorDataBlock("GPS2 Fix", "---")
        self.block_ekf_pos = SensorDataBlock("EKF Health", "WAIT", "#ffaa00")
        self.block_wp_dist = SensorDataBlock("Target Dist", "0 m")
        self.block_viz_lock = SensorDataBlock("Vision Lock", "SEARCHING", "#92b0c3")
        
        body_layout.addWidget(self._create_separator())
        body_layout.addWidget(self.block_gps_stat)
        body_layout.addWidget(self.block_airspeed)
        body_layout.addWidget(self.block_gps2_fix)
        body_layout.addWidget(self.block_ekf_pos)
        body_layout.addWidget(self.block_wp_dist)
        body_layout.addWidget(self.block_viz_lock)
        
        self.body_widget.setVisible(False)
        main_layout.addWidget(self.body_widget)
        
    def _create_separator(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: rgba(0, 221, 255, 0.1); max-height: 1px; border: none;")
        return line
        
    def toggle_expansion(self):
        self.is_expanded = not self.is_expanded
        self.body_widget.setVisible(self.is_expanded)
        
    # --- UPDATE METHODS ---
    def update_basic(self, mode=None, alt=None, batt=None):
        if mode is not None: self.lbl_mode.setText(f"MODE: {mode}")
        if alt is not None: self.lbl_alt.setText(f"ALT: {alt:.1f}m")
        if batt is not None: self.lbl_batt.setText(f"BATT: {batt:.1f}V")

    def update_sensors(self, airspeed=None, gps_active=None):
        if airspeed is not None: self.block_airspeed.set_value(f"{airspeed:.1f} m/s")
        if gps_active is not None:
            status = "ACTIVE" if gps_active else "LOST/DENIED"
            color = "#00ff78" if gps_active else "#ff3232"
            self.block_gps_stat.set_value(status, color)

    def update_trn(self, fix_type=None, hdop=None, ekf_flags=None):
        if fix_type is not None:
            self.block_gps2_fix.set_value(f"{fix_type} (3D)" if fix_type >= 3 else f"{fix_type} (None)")
        if ekf_flags is not None:
            ok = (ekf_flags & 8) != 0 # EKF_POS_HORIZ_ABS
            self.block_ekf_pos.set_value("PASS" if ok else "FAIL", "#00ff78" if ok else "#ff3232")

    def update_nav(self, wp_dist=None):
        if wp_dist is not None: self.block_wp_dist.set_value(f"{int(wp_dist)} m")

    def update_vision(self, status, conf, off_x, off_y):
        color = "#00ff78" if status == "LOCKED" else ("#ffaa00" if status == "LOST" else "#92b0c3")
        self.block_viz_lock.set_value(status, color)


class SensorPanel(QFrame):
    """Fleet-Aware Tactical Slide-out Sensor & Navigation Panel 🛰️"""
    close_requested = Signal() # Emitted when user clicks the close button

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(240) # Slightly wider for the list view
        self.cards = {} # Mapping of f"{n_id}:{s_id}" -> DroneSensorCard
        
        self.setObjectName("sensorPanel")
        self.setStyleSheet("""
            #sensorPanel {
                background-color: rgba(9, 21, 28, 0.96);
                border: 1px solid rgba(0, 221, 255, 0.35);
                border-radius: 10px;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: rgba(9, 14, 17, 0.5);
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(0, 221, 255, 0.3);
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(0, 221, 255, 0.6);
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header Area (Matching Mission Planner)
        header_widget = QWidget()
        header_widget.setStyleSheet("""
            background-color: rgba(0, 221, 255, 0.1); 
            border-bottom: 1px solid rgba(0, 221, 255, 0.2);
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
        """)
        header_lay = QHBoxLayout(header_widget)
        header_lay.setContentsMargins(12, 12, 12, 12)
        
        header = QLabel("SWARM TELEMETRY")
        header.setStyleSheet("color: #00ddff; font-size: 13px; font-weight: bold; letter-spacing: 1px; border: none; background: transparent;")
        
        self.btn_close = QPushButton("✕")
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.setStyleSheet("background-color: transparent; color: #ff3232; font-weight: bold; border: none; font-size: 14px; padding: 0px 5px;")
        self.btn_close.clicked.connect(self.close_requested.emit)
        
        header_lay.addWidget(header)
        header_lay.addStretch()
        header_lay.addWidget(self.btn_close)
        main_layout.addWidget(header_widget)
        
        # Scroll Area Container
        scroll_container = QWidget()
        scroll_container.setStyleSheet("background: transparent; border: none;")
        scroll_container_lay = QVBoxLayout(scroll_container)
        scroll_container_lay.setContentsMargins(8, 12, 8, 12)
        
        # Scroll Area for Drone Cards
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent; border: none;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(8)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        
        self.scroll_area.setWidget(self.scroll_content)
        scroll_container_lay.addWidget(self.scroll_area)
        
        main_layout.addWidget(scroll_container)

    def _get_or_create_card(self, n_id, s_id):
        key = f"{n_id}:{s_id}"
        if key not in self.cards:
            card = DroneSensorCard(n_id, s_id)
            self.cards[key] = card
            self.scroll_layout.addWidget(card)
        return self.cards[key]

    # --- ROUTING METHODS ---
    def update_basic(self, n_id, s_id, mode=None, alt=None, batt=None):
        self._get_or_create_card(n_id, s_id).update_basic(mode=mode, alt=alt, batt=batt)

    def update_sensors(self, n_id, s_id, airspeed=None, gps_active=None):
        self._get_or_create_card(n_id, s_id).update_sensors(airspeed=airspeed, gps_active=gps_active)

    def update_trn(self, n_id, s_id, fix_type=None, hdop=None, ekf_flags=None):
        self._get_or_create_card(n_id, s_id).update_trn(fix_type=fix_type, hdop=hdop, ekf_flags=ekf_flags)

    def update_nav(self, n_id, s_id, wp_dist=None):
        self._get_or_create_card(n_id, s_id).update_nav(wp_dist=wp_dist)

    def update_vision(self, n_id, s_id, status, conf, off_x, off_y):
        self._get_or_create_card(n_id, s_id).update_vision(status, conf, off_x, off_y)
