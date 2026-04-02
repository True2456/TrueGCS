import serial.tools.list_ports
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QComboBox, QTabWidget, QPlainTextEdit
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QIcon

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
        self.resize(1000, 750)

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
        layout.setContentsMargins(10, 10, 10, 10)

        self.combo_target_drone = QComboBox()
        self.combo_target_drone.setFixedWidth(220)
        self.combo_target_drone.addItem("No Drones Detected", userData=None)
        self.combo_target_drone.setStyleSheet("font-weight: bold; color: #00ddff;")

        self.btn_disconnect_node = QPushButton("Disconnect Node")
        self.btn_disconnect_node.setStyleSheet("background-color: rgba(255, 50, 50, 0.15); border: 1px solid #ff3232; color: #ffffff;")
        self.btn_disconnect_node.setFixedWidth(130)

        self.combo_type = QComboBox()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.combo_type.addItem(f"Serial: {port.device} - {port.description}", userData=("serial", port.device))
        self.combo_type.addItem("Network: UDP", userData=("udp", ""))
        self.combo_type.addItem("Network: TCP", userData=("tcp", ""))
        self.combo_type.currentIndexChanged.connect(self.on_connection_type_changed)

        self.lbl_p1 = QLabel("Baud:")
        self.txt_p1 = QLineEdit("115200")
        self.txt_p1.setFixedWidth(100)
        
        self.lbl_p2 = QLabel("Port:")
        self.txt_p2 = QLineEdit("14550")
        self.txt_p2.setFixedWidth(80)
        self.lbl_p2.hide()
        self.txt_p2.hide()

        # Phase 1.9: Connection UI Sync (Force initial state to match combo selection)
        self.on_connection_type_changed()

        self.btn_add_node = QPushButton("+ Add Node")
        self.btn_add_node.setStyleSheet("background-color: rgba(0, 221, 255, 0.15); border: 1px solid #00ddff; color: #ffffff;")
        
        self.combo_mode = QComboBox()
        self.combo_mode.setFixedWidth(110)
        self.combo_mode.hide()
        self.combo_mode.currentTextChanged.connect(self.on_mode_selected)
        
        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet("color: #92b0c3; font-size: 14px;")

        self.btn_set_mode = QPushButton("SET")
        self.btn_set_mode.setFixedWidth(50)
        self.btn_set_mode.setStyleSheet("background-color: rgba(0, 255, 0, 0.1); border: 1px solid #00ff00; color: #fff;")
        
        # New Arm/Disarm Button 🛰️
        self.btn_arm = QPushButton("DISARMED")
        self.btn_arm.setFixedWidth(100)
        self.btn_arm.setStyleSheet("background-color: rgba(255, 50, 50, 0.1); border: 1px solid #ff3232; color: #fff; font-weight: bold;")
        
        layout.addWidget(QLabel("ACTIVE TARGET:"))
        layout.addWidget(self.combo_target_drone)
        layout.addWidget(self.btn_disconnect_node)
        layout.addSpacing(10)
        layout.addWidget(self.btn_arm)
        layout.addSpacing(10)
        layout.addWidget(QLabel("  FLIGHT MODE:"))
        layout.addWidget(self.combo_mode)
        layout.addWidget(self.btn_set_mode)
        
        layout.addStretch()
        
        layout.addWidget(QLabel("NEW NODE:"))
        layout.addWidget(self.combo_type)
        layout.addWidget(self.lbl_p1)
        layout.addWidget(self.txt_p1)
        layout.addWidget(self.lbl_p2)
        layout.addWidget(self.txt_p2)
        layout.addWidget(self.btn_add_node)
        layout.addSpacing(15)
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
                self.combo_type.addItem(f"Serial: {port.device} - {port.description}", userData=("serial", port.device))
            self.combo_type.addItem("Network: UDP", userData=("udp", ""))
            self.combo_type.addItem("Network: TCP", userData=("tcp", ""))
            
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

    def closeEvent(self, event):
        # The main.py will handle shutting down all telemetry nodes when app exits
        if self.video_thread:
            self.video_thread.stop()
        event.accept()
