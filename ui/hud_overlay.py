from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, QPointF
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

class SensorPanel(QFrame):
    """Tactical Slide-out Sensor & Navigation Status Panel 🛰️"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(180)
        self._gps_active = True # Track state to avoid flickering 🛡️
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(9, 14, 17, 0.9);
                border-left: 2px solid #00ddff;
                border-bottom-left-radius: 10px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # Header
        header = QLabel("TACTICAL MONITOR")
        header.setStyleSheet("color: #00ddff; font-size: 10px; font-weight: bold; letter-spacing: 2px;")
        layout.addWidget(header)
        
        # Section: Avionics
        layout.addWidget(self._create_separator())
        self.block_alt_lidar = SensorDataBlock("Lidar (SF20)")
        self.block_airspeed = SensorDataBlock("Airspeed")
        self.block_gps_stat = SensorDataBlock("GPS Status", "ACTIVE", "#00ff78")
        
        layout.addWidget(self.block_alt_lidar)
        layout.addWidget(self.block_airspeed)
        layout.addWidget(self.block_gps_stat)
        
        # Section: TRN Diagnostics 🛰️
        trn_header = QLabel("TRN / NAVIGATION")
        trn_header.setStyleSheet("color: #92b0c3; font-size: 8px; font-weight: bold; margin-top: 5px;")
        layout.addWidget(trn_header)
        layout.addWidget(self._create_separator())
        
        self.block_gps2_fix = SensorDataBlock("GPS2 Fix", "---")
        self.block_gps2_hdop = SensorDataBlock("PSR Conf", "---")
        self.block_ekf_pos = SensorDataBlock("EKF Health", "WAIT", "#ffaa00")
        self.block_wp_dist = SensorDataBlock("Target Dist", "0 m")
        
        layout.addWidget(self.block_gps2_fix)
        layout.addWidget(self.block_gps2_hdop)
        layout.addWidget(self.block_ekf_pos)
        layout.addWidget(self.block_wp_dist)

        # Section: Visual Navigation
        vnav_header = QLabel("VISUAL LOCK")
        vnav_header.setStyleSheet("color: #92b0c3; font-size: 8px; font-weight: bold; margin-top: 5px;")
        layout.addWidget(vnav_header)
        layout.addWidget(self._create_separator())
        
        self.block_viz_lock = SensorDataBlock("State", "SEARCHING", "#92b0c3")
        self.block_viz_conf = SensorDataBlock("Confidence", "0%")
        self.block_viz_offset = SensorDataBlock("Px Offset", "0, 0")
        
        layout.addWidget(self.block_viz_lock)
        layout.addWidget(self.block_viz_conf)
        layout.addWidget(self.block_viz_offset)
        
        # Section: AI Reconnaissance 🚀
        ai_header = QLabel("AI RECONNAISSANCE")
        ai_header.setStyleSheet("color: #92b0c3; font-size: 8px; font-weight: bold; margin-top: 5px;")
        layout.addWidget(ai_header)
        layout.addWidget(self._create_separator())
        
        self.block_ai_model = SensorDataBlock("Model", "---")
        self.block_ai_fps_inf = SensorDataBlock("AI FPS", "0", "#00ff78")
        self.block_ai_fps_vid = SensorDataBlock("Feed FPS", "0", "#00ddff")
        
        layout.addWidget(self.block_ai_model)
        layout.addWidget(self.block_ai_fps_inf)
        layout.addWidget(self.block_ai_fps_vid)
        
        layout.addStretch()
        
        # Footer: Active ID
        self.lbl_active_id = QLabel("NODE: ---")
        self.lbl_active_id.setStyleSheet("color: rgba(0, 221, 255, 0.4); font-size: 8px; font-family: 'Consolas';")
        self.lbl_active_id.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_active_id)

    def _create_separator(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: rgba(0, 221, 255, 0.1); max-height: 1px;")
        return line

    def update_sensors(self, lidar_alt=None, airspeed=None, gps_active=None):
        if lidar_alt is not None: self.block_alt_lidar.set_value(f"{lidar_alt:.2f} m")
        if airspeed is not None: self.block_airspeed.set_value(f"{airspeed:.1f} m/s")
        
        # Only update label if state explicitly changed OR on first init 🛡️
        if gps_active is not None:
             self._gps_active = gps_active

        status = "ACTIVE" if self._gps_active else "LOST/DENIED"
        color = "#00ff78" if self._gps_active else "#ff3232"
        self.block_gps_stat.set_value(status, color)

    def update_trn(self, fix_type=None, hdop=None, ekf_flags=None):
        if fix_type is not None:
            self.block_gps2_fix.set_value(f"{fix_type} (3D)" if fix_type >= 3 else f"{fix_type} (None)")
        if hdop is not None:
            # Map HDOP back to a readable PSR "Quality" or just show HDOP 🛰️
            self.block_gps2_hdop.set_value(f"{hdop:.2f}")
        if ekf_flags is not None:
            # Check Bit 3 (val 8): EKF_POS_HORIZ_ABS
            ok = (ekf_flags & 8) != 0
            self.block_ekf_pos.set_value("PASS" if ok else "FAIL", "#00ff78" if ok else "#ff3232")

    def update_nav(self, wp_dist=None):
        if wp_dist is not None:
            self.block_wp_dist.set_value(f"{int(wp_dist)} m")

    def update_vision(self, status, conf, off_x, off_y):
        color = "#00ff78" if status == "LOCKED" else ("#ffaa00" if status == "LOST" else "#92b0c3")
        self.block_viz_lock.set_value(status, color)
        self.block_viz_conf.set_value(f"{int(conf*100)}%")
        self.block_viz_offset.set_value(f"{off_x}, {off_y}")

    def update_ai_diagnostics(self, model, inf_fps, vid_fps):
        """Update the Reconnaissance AI performance blocks 🚀"""
        self.block_ai_model.set_value(model)
        self.block_ai_fps_inf.set_value(int(inf_fps))
        self.block_ai_fps_vid.set_value(int(vid_fps))

    def set_active_node(self, node_name):
        self.lbl_active_id.setText(f"ACTIVE NODE: {node_name}")
