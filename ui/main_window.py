import serial.tools.list_ports
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QComboBox, QTabWidget, QPlainTextEdit, QApplication, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QPixmap, QIcon


class CompactComboBox(QComboBox):
    """QComboBox that caps its minimumSizeHint to its fixed/maximum width so the
    macOS native style can't inflate the window's minimum size via long item text."""
    def minimumSizeHint(self):
        base = super().minimumSizeHint()
        cap  = self.maximumWidth()
        return QSize(min(base.width(), cap), base.height())

    def sizeHint(self):
        base = super().sizeHint()
        cap  = self.maximumWidth()
        return QSize(min(base.width(), cap), base.height())

from ui.styles import BF3_STYLE
from ui.tabs_ops import OpsTab
from ui.tabs_cfg import CfgTab
from ui.tabs_video import VideoTab
from core.pid_controller import GimbalPIDController

class GCSMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ISR GCS")
        self.setStyleSheet(BF3_STYLE)

        self.telemetry = None
        self.video_thread = None
        self.pid_controller = GimbalPIDController(self)
        
        # 'Hot-Plug' Detector (Scan for new ports every 2s)
        self.port_timer = QTimer(self)
        self.port_timer.timeout.connect(self.refresh_conn_ports)
        self.port_timer.start(2000)

        self.setWindowIcon(QIcon("resources/icons/drone_icon.png"))
        self._first_show = True  # Guard so we only auto-size once

        # Mission Logging Console
        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMaximumHeight(150)
        self.log_console.setStyleSheet("background-color: #05080a; color: #00ddff; font-family: 'Consolas'; border: 1px solid #111a22;")
        self.log_console.hide() # Hidden by default, toggled from Ops tab

        self.init_ui()

    def init_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(5, 5, 5, 5) # Tightened cockpit

        # Top connection bar
        conn_bar = self.create_connection_bar()
        self.main_layout.addWidget(conn_bar)

        # Tabs
        self.tabs = QTabWidget()
        self.tab_ops = OpsTab()
        self.tab_video = VideoTab()
        self.tab_cfg = CfgTab()
        
        # Link Cfg Tab status label to connection bar status label
        self.tab_cfg.lbl_status = self.lbl_status
        
        self.tabs.addTab(self.tab_ops, "Operations")
        self.tabs.addTab(self.tab_video, "Video & Detection")
        self.tabs.addTab(self.tab_cfg, "Configuration")
        
        self.main_layout.addWidget(self.tabs)
        self.main_layout.addWidget(self.log_console)

    def create_connection_bar(self):
        bar = QWidget()
        bar.setStyleSheet("background-color: #111a22; border: 1px solid #2a4555;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(6, 6, 6, 6)  # Was 10,10,10,10
        layout.setSpacing(4)                    # Was default ~6px

        self.combo_target_drone = CompactComboBox()
        self.combo_target_drone.setFixedWidth(160)  # Was 220
        self.combo_target_drone.addItem("No Drones", userData=None)
        self.combo_target_drone.setStyleSheet("font-weight: bold; color: #00ddff;")
        self.combo_target_drone.setToolTip("Active target drone")

        self.btn_disconnect_node = QPushButton("✕ Node")
        self.btn_disconnect_node.setStyleSheet("background-color: rgba(255, 50, 50, 0.15); border: 1px solid #ff3232; color: #ffffff;")
        self.btn_disconnect_node.setFixedWidth(70)  # Was 130
        self.btn_disconnect_node.setToolTip("Disconnect active node")

        self.combo_type = CompactComboBox()
        self.combo_type.setFixedWidth(165)  # Was 185
        self.combo_type.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        ports = serial.tools.list_ports.comports()
        for port in ports:
            label = f"Serial: {port.device}"
            self.combo_type.addItem(label, userData=("serial", port.device))
            self.combo_type.setItemData(self.combo_type.count() - 1,
                                        f"{port.device} — {port.description}",
                                        Qt.ToolTipRole)
        self.combo_type.addItem("UDP", userData=("udp", ""))
        self.combo_type.addItem("TCP", userData=("tcp", ""))
        self.combo_type.currentIndexChanged.connect(self.on_connection_type_changed)

        self.lbl_p1 = QLabel("Baud:")
        self.txt_p1 = QLineEdit("115200")
        self.txt_p1.setFixedWidth(80)   # Was 100
        
        self.lbl_p2 = QLabel("Port:")
        self.txt_p2 = QLineEdit("14550")
        self.txt_p2.setFixedWidth(70)   # Was 80
        self.lbl_p2.hide()
        self.txt_p2.hide()

        self.on_connection_type_changed()

        self.btn_add_node = QPushButton("+ Add")
        self.btn_add_node.setFixedWidth(70)  # Was 90
        self.btn_add_node.setToolTip("Add connection node")
        self.btn_add_node.setStyleSheet("background-color: rgba(0, 221, 255, 0.15); border: 1px solid #00ddff; color: #ffffff;")
        
        self.combo_mode = CompactComboBox()
        self.combo_mode.setFixedWidth(100)  # Was 110
        self.combo_mode.hide()
        self.combo_mode.currentTextChanged.connect(self.on_mode_selected)
        
        self.lbl_status = QLabel("Ready")
        self.lbl_status.setMaximumWidth(180)  # Was 220
        self.lbl_status.setStyleSheet("color: #92b0c3; font-size: 12px;")

        self.btn_set_mode = QPushButton("SET")
        self.btn_set_mode.setFixedWidth(44)  # Was 50
        self.btn_set_mode.setStyleSheet("background-color: rgba(0, 255, 0, 0.1); border: 1px solid #00ff00; color: #fff;")
        
        self.btn_arm = QPushButton("DISARMED")
        self.btn_arm.setFixedWidth(90)  # Was 100
        self.btn_arm.setStyleSheet("background-color: rgba(255, 50, 50, 0.1); border: 1px solid #ff3232; color: #fff; font-weight: bold;")
        
        # Left side: target/arm/mode
        layout.addWidget(QLabel("TGT:"))
        layout.addWidget(self.combo_target_drone)
        layout.addWidget(self.btn_disconnect_node)
        layout.addWidget(self.btn_arm)
        layout.addWidget(QLabel("MODE:"))
        layout.addWidget(self.combo_mode)
        layout.addWidget(self.btn_set_mode)
        layout.addStretch()
        # Right side: new node connection
        layout.addWidget(QLabel("NODE:"))
        layout.addWidget(self.combo_type)
        layout.addWidget(self.lbl_p1)
        layout.addWidget(self.txt_p1)
        layout.addWidget(self.lbl_p2)
        layout.addWidget(self.txt_p2)
        layout.addWidget(self.btn_add_node)
        layout.addWidget(self.lbl_status)
        
        return bar

    def refresh_conn_ports(self):
        """Monitors and updates the available serial ports in real-time."""
        if not hasattr(self, 'combo_type'):
            return
            
        ports = serial.tools.list_ports.comports()
        current_data = [self.combo_type.itemData(i) for i in range(self.combo_type.count())]
        
        new_serial_ports = [("serial", p.device) for p in ports]
        # Always include static network options
        total_target_data = new_serial_ports + [("udp", ""), ("tcp", "")]
        
        if current_data != total_target_data:
            print("Dashboard: Syncing new hardware configuration...")
            # Save current selection by value (userData)
            prev_sel_data = self.combo_type.currentData()
            
            self.combo_type.blockSignals(True)
            self.combo_type.clear()
            for port in ports:
                label = f"Serial: {port.device}"
                self.combo_type.addItem(label, userData=("serial", port.device))
                self.combo_type.setItemData(self.combo_type.count() - 1,
                                            f"{port.device} — {port.description}",
                                            Qt.ToolTipRole)
            self.combo_type.addItem("UDP", userData=("udp", ""))
            self.combo_type.addItem("TCP", userData=("tcp", ""))
            
            # Restore selection
            for i in range(self.combo_type.count()):
                if self.combo_type.itemData(i) == prev_sel_data:
                    self.combo_type.setCurrentIndex(i)
                    break
            self.combo_type.blockSignals(False)

    def on_connection_type_changed(self):
        ctype, _ = self.combo_type.currentData()
        if ctype == "serial":
            self.lbl_p1.setText("Baud:")
            self.txt_p1.setText("115200")
            self.lbl_p2.hide()
            self.txt_p2.hide()
        elif ctype == "udp":
            self.lbl_p1.setText("Port:")
            self.txt_p1.setText("15550")
            self.lbl_p2.hide()
            self.txt_p2.hide()
        else:
            self.lbl_p1.setText("IP:")
            self.txt_p1.setText("127.0.0.1")
            self.lbl_p2.show()
            self.txt_p2.show()

    def update_video_frame(self, img):
        self.tab_ops.video_label.set_source_frame_size(img.width(), img.height())
        pixmap = QPixmap.fromImage(img)
        scaled = pixmap.scaled(self.tab_ops.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.tab_ops.video_label.setPixmap(scaled)

    def on_heartbeat(self, success):
        if success:
            self.lbl_status.setText("MAVLink: Connected [Heartbeat OK]")
            self.lbl_status.setStyleSheet("color: #00ddff; font-size: 14px;")
        else:
            self.lbl_status.setText("MAVLink: Connection Failed")
            self.lbl_status.setStyleSheet("color: red; font-size: 14px;")
            
    def on_params_loaded(self):
        self.lbl_status.setText("MAVLink: Parameters Synced")

    def populate_flight_modes(self, modes):
        self.combo_mode.blockSignals(True)
        self.combo_mode.clear()
        self.combo_mode.addItems(modes)
        self.combo_mode.show()
        self.combo_mode.blockSignals(False)

    def on_mode_selected(self, mode):
        # We will dynamically grab the active drone from the core manager, 
        # so this UI just emits the intent to change mode
        pass

    def showEvent(self, event):
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            # Defer until after the window is actually mapped by the OS.
            # resize()/move() called before show() are silently ignored on macOS.
            QTimer.singleShot(0, self._fit_to_screen)

    def _fit_to_screen(self):
        """Resize and centre the window so it always fits within the available
        screen area on any platform/DPI scale."""
        screen = self.screen() or QApplication.primaryScreen()
        if not screen:
            return
        avail = screen.availableGeometry()
        w = min(int(avail.width()  * 0.92), 1400)
        h = min(int(avail.height() * 0.92),  900)
        from PySide6.QtWidgets import QLayout
        self.main_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        # Cap the maximum so macOS commits the resize before we restore bounds.
        self.setMaximumSize(w, h)
        self.resize(w, h)
        # Read actual size (resize may be clamped)
        actual_w = self.width()
        actual_h = self.height()
        x = avail.x() + max(0, (avail.width()  - actual_w) // 2)
        y = avail.y() + max(0, (avail.height() - actual_h) // 2)
        x = min(x, avail.x() + avail.width()  - actual_w)
        y = min(y, avail.y() + avail.height() - actual_h)
        x = max(x, avail.x())
        y = max(y, avail.y())
        self.move(x, y)
        QTimer.singleShot(150, lambda: (
            self.setMaximumSize(16777215, 16777215),
            self.setMinimumSize(0, 0),
        ))

    def closeEvent(self, event):
        # The main.py will handle shutting down all telemetry nodes when app exits
        if self.video_thread:
            self.video_thread.stop()
        event.accept()
