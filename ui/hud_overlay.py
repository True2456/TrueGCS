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
        self.hud_speed = HUDLabel("Grd Speed", "m/s")
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
