import sys
import os
import subprocess
import threading
from core.utils import find_binary
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QPlainTextEdit, QGroupBox, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject

class _DJILogSignaler(QObject):
    """Bridge subprocess stderr → Qt signal (thread-safe)."""
    line_received = Signal(str)

class DJITab(QWidget):
    """
    DJI Config Tab: Manages an FFmpeg RTMP-to-UDP relay.
    Acts as a listener server for DJI drone video streams.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.relay_process = None
        self.signaler = _DJILogSignaler()
        self.signaler.line_received.connect(self._update_log)
        self.local_ip = self.get_local_ip()
        self.init_ui()

    def get_local_ip(self):
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 1. Configuration Group
        cfg_group = QGroupBox("Relay Configuration")
        cfg_group.setStyleSheet("QGroupBox { font-weight: bold; color: #00ddff; border: 1px solid #2a4555; margin-top: 10px; padding-top: 10px; }")
        cfg_lay = QVBoxLayout(cfg_group)

        # RTMP Input
        rtmp_row = QHBoxLayout()
        rtmp_row.addWidget(QLabel("RTMP Server Port:"))
        self.txt_rtmp_port = QLineEdit("15560")
        self.txt_rtmp_port.setPlaceholderText("e.g. 15560")
        self.txt_rtmp_port.setFixedWidth(100)
        self.txt_rtmp_port.textChanged.connect(self._update_rtmp_url_label)
        rtmp_row.addWidget(self.txt_rtmp_port)
        rtmp_row.addStretch()
        
        self.lbl_rtmp_url = QLabel(f"Drone RTMP URL: rtmp://{self.local_ip}:15560/live/drone")
        self.lbl_rtmp_url.setStyleSheet("color: #00ddff; font-size: 12px; font-weight: bold;")
        
        cfg_lay.addLayout(rtmp_row)
        cfg_lay.addWidget(self.lbl_rtmp_url)

        # UDP Output
        udp_row = QHBoxLayout()
        udp_row.addWidget(QLabel("UDP Output Port:"))
        self.txt_udp_port = QLineEdit("5008")
        self.txt_udp_port.setPlaceholderText("e.g. 5008")
        self.txt_udp_port.setFixedWidth(100)
        udp_row.addWidget(self.txt_udp_port)
        udp_row.addStretch()
        
        cfg_lay.addLayout(udp_row)

        layout.addWidget(cfg_group)

        # 2. Control Button
        self.btn_toggle = QPushButton("▶ Launch DJI Relay")
        self.btn_toggle.setMinimumHeight(45)
        self.btn_toggle.setStyleSheet("""
            QPushButton {
                background-color: #0d1a24;
                border: 1px solid #00ddff;
                color: #00ddff;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #1a3040; }
        """)
        self.btn_toggle.clicked.connect(self.toggle_relay)
        layout.addWidget(self.btn_toggle)

        # 3. Live Log
        log_group = QGroupBox("FFmpeg Relay Output")
        log_group.setStyleSheet("QGroupBox { font-weight: bold; color: #888888; border: 1px solid #2a4555; }")
        log_lay = QVBoxLayout(log_group)
        
        self.log_area = QPlainTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("background-color: #05080a; color: #00ff00; font-family: 'Consolas', monospace; font-size: 12px;")
        self.log_area.setPlaceholderText("Waiting for relay startup...")
        log_lay.addWidget(self.log_area)
        
        layout.addWidget(log_group)

        layout.addStretch()

    def _update_log(self, text):
        self.log_area.appendPlainText(text.strip())
        # Auto-scroll
        vbar = self.log_area.verticalScrollBar()
        vbar.setValue(vbar.maximum())

    def _update_rtmp_url_label(self):
        port = self.txt_rtmp_port.text().strip() or "15560"
        self.lbl_rtmp_url.setText(f"Drone RTMP URL: rtmp://{self.local_ip}:{port}/live/drone")

    def toggle_relay(self):
        if self.relay_process is None:
            self.start_relay()
        else:
            self.stop_relay()

    def start_relay(self):
        rtmp_port = self.txt_rtmp_port.text().strip()
        udp_port = self.txt_udp_port.text().strip()

        # Build FFmpeg command 🚀 using the robust binary locator
        ffmpeg_bin = find_binary("ffmpeg")
        
        cmd = [
            ffmpeg_bin,
            "-hide_banner", "-loglevel", "error",
            "-probesize", "32",
            "-analyzeduration", "0",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-listen", "1",
            "-i", f"rtmp://0.0.0.0:{rtmp_port}/live/drone",
            "-c:v", "copy",
            "-f", "mpegts",
            f"udp://127.0.0.1:{udp_port}?pkt_size=1316"
        ]

        try:
            self.relay_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            # Start reader thread for stderr (FFmpeg logs to stderr)
            threading.Thread(target=self._read_output, args=(self.relay_process.stderr,), daemon=True).start()
            
            self.btn_toggle.setText("■ Stop DJI Relay")
            self.btn_toggle.setStyleSheet("background-color: #3d0d0d; border: 1px solid #ff3232; color: #ff3232; font-weight: bold; font-size: 14px;")
            self.log_area.appendPlainText(f"[RELAY] Server listening on RTMP port {rtmp_port}...")
            
        except Exception as e:
            self.log_area.appendPlainText(f"[ERROR] Failed to launch FFmpeg: {e}")

    def _read_output(self, pipe):
        try:
            for line in iter(pipe.readline, ''):
                if not line: break
                self.signaler.line_received.emit(line)
        except:
            pass

    def stop_relay(self):
        if self.relay_process:
            self.relay_process.terminate()
            try:
                self.relay_process.wait(timeout=2)
            except:
                self.relay_process.kill()
            self.relay_process = None
            
        self.btn_toggle.setText("▶ Launch DJI Relay")
        self.btn_toggle.setStyleSheet("background-color: #0d1a24; border: 1px solid #00ddff; color: #00ddff; font-weight: bold; font-size: 14px;")
        self.log_area.appendPlainText("[RELAY] Stopped.")

    def stop_all(self):
        """Cleanup for app exit."""
        self.stop_relay()
