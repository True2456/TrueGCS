import sys
import os
import subprocess
import threading

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QPlainTextEdit, QGroupBox, QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject


class _SimLogSignaler(QObject):
    """Bridge subprocess stdout → Qt signal (thread-safe)."""
    line_received = Signal(str)


class SimInstance(QFrame):
    """A single simulation instance row — port input, launch/stop, status."""

    def __init__(self, instance_id: int, log_fn, on_remove, parent=None):
        super().__init__(parent)
        self._id = instance_id
        self._log = log_fn          # callable(str) to write to shared log
        self._on_remove = on_remove # callable() to remove this row
        self._process = None
        self._poll_timer = None
        self._signaler = _SimLogSignaler()
        self._signaler.line_received.connect(self._route_log)

        self.setStyleSheet("""
            QFrame {
                background-color: #0d1a24;
                border: 1px solid #2a4555;
                border-radius: 6px;
            }
        """)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._build()

    def _build(self):
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(10)

        # Instance label
        id_lbl = QLabel(f"SIM {self._id}")
        id_lbl.setFixedWidth(44)
        id_lbl.setStyleSheet("color: #00ddff; font-weight: bold; font-size: 12px;")
        row.addWidget(id_lbl)

        # Port
        port_lbl = QLabel("Port:")
        port_lbl.setStyleSheet("color: #92b0c3; font-size: 12px;")
        row.addWidget(port_lbl)

        self.txt_port = QLineEdit(str(14549 + self._id))  # 14550, 14551, …
        self.txt_port.setFixedWidth(72)
        self.txt_port.setStyleSheet(
            "background: #05080a; color: #fff; border: 1px solid #2a4555; "
            "border-radius: 4px; padding: 3px 6px; font-size: 12px;"
        )
        row.addWidget(self.txt_port)

        # Launch button
        self.btn_launch = QPushButton("▶ Launch")
        self.btn_launch.setFixedSize(90, 28)
        self.btn_launch.setStyleSheet(
            "background: rgba(0,221,255,0.12); border: 1px solid #00ddff; "
            "color: #fff; font-weight: bold; border-radius: 4px; font-size: 11px;"
        )
        self.btn_launch.clicked.connect(self._launch)
        row.addWidget(self.btn_launch)

        # Stop button
        self.btn_stop = QPushButton("■ Stop")
        self.btn_stop.setFixedSize(70, 28)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet(
            "background: rgba(255,50,50,0.12); border: 1px solid #ff3232; "
            "color: #fff; font-weight: bold; border-radius: 4px; font-size: 11px;"
        )
        self.btn_stop.clicked.connect(self._stop)
        row.addWidget(self.btn_stop)

        # Status dot
        self.dot = QLabel("●")
        self.dot.setStyleSheet("color: #333; font-size: 14px;")
        row.addWidget(self.dot)

        self.lbl_status = QLabel("Idle")
        self.lbl_status.setStyleSheet("color: #92b0c3; font-size: 11px;")
        row.addWidget(self.lbl_status)

        row.addStretch()

        # Remove button (only when idle)
        self.btn_remove = QPushButton("✕")
        self.btn_remove.setFixedSize(26, 26)
        self.btn_remove.setToolTip("Remove this simulation instance")
        self.btn_remove.setStyleSheet(
            "background: transparent; border: 1px solid #2a4555; "
            "color: #92b0c3; border-radius: 4px; font-size: 12px;"
        )
        self.btn_remove.clicked.connect(self._on_remove)
        row.addWidget(self.btn_remove)

    # ------------------------------------------------------------------ #
    def _launch(self):
        port_text = self.txt_port.text().strip()
        try:
            port = int(port_text)
            if not (1024 <= port <= 65535):
                raise ValueError
        except ValueError:
            self._log(f"[SIM {self._id}] ERROR: Invalid port '{port_text}'")
            return

        python_exe = sys.executable
        sim_script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "simulation", "vtol_sim.py"
        )

        self._log(f"[SIM {self._id}] Launching on UDP:{port} ...")
        try:
            self._process = subprocess.Popen(
                [python_exe, sim_script, "--port", str(port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as e:
            self._log(f"[SIM {self._id}] Launch failed: {e}")
            return

        self._set_running(True, port)
        threading.Thread(target=self._stream, daemon=True).start()

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._check_alive)
        self._poll_timer.start(500)

    def _stop(self):
        if self._process and self._process.poll() is None:
            self._log(f"[SIM {self._id}] Stopping...")
            self._process.terminate()
            QTimer.singleShot(2000, self._force_kill)

    def _force_kill(self):
        if self._process and self._process.poll() is None:
            self._process.kill()

    def _stream(self):
        try:
            for line in self._process.stdout:
                self._signaler.line_received.emit(line.rstrip())
        except Exception:
            pass

    def _route_log(self, text: str):
        self._log(f"[SIM {self._id}] {text}")

    def _check_alive(self):
        if self._process and self._process.poll() is not None:
            self._poll_timer.stop()
            rc = self._process.returncode
            self._log(f"[SIM {self._id}] Stopped (exit {rc}).")
            self._set_running(False)

    def _set_running(self, running: bool, port: int = 0):
        self.btn_launch.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.txt_port.setEnabled(not running)
        self.btn_remove.setEnabled(not running)
        if running:
            self.dot.setStyleSheet("color: #33ff55; font-size: 14px;")
            self.lbl_status.setText(f"Running  UDP:{port}")
            self.lbl_status.setStyleSheet("color: #33ff55; font-size: 11px;")
        else:
            self.dot.setStyleSheet("color: #333; font-size: 14px;")
            self.lbl_status.setText("Idle")
            self.lbl_status.setStyleSheet("color: #92b0c3; font-size: 11px;")

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def stop_and_wait(self):
        """Called when the whole GCS is closing."""
        if self.is_running():
            self._process.terminate()


# ======================================================================= #
#  SimTab                                                                   #
# ======================================================================= #
class SimTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._instances: list[SimInstance] = []
        self._next_id = 1
        self._build_ui()
        self._add_instance()  # start with one row ready to go

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # ── Header ────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("VTOL Simulator")
        title.setStyleSheet(
            "color: #00ddff; font-size: 18px; font-weight: bold; letter-spacing: 2px;"
        )
        hdr.addWidget(title)
        hdr.addStretch()

        self.btn_add = QPushButton("＋  Add Simulation")
        self.btn_add.setFixedHeight(32)
        self.btn_add.setStyleSheet(
            "background: rgba(0,221,255,0.12); border: 1px solid #00ddff; "
            "color: #fff; font-weight: bold; border-radius: 4px; padding: 0 14px;"
        )
        self.btn_add.clicked.connect(self._add_instance)
        hdr.addWidget(self.btn_add)
        root.addLayout(hdr)

        sub = QLabel(
            "Each row is an independent SITL instance. "
            "Assign a unique UDP port per simulation and connect via the NODE bar above."
        )
        sub.setStyleSheet("color: #92b0c3; font-size: 11px;")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # ── Instance list (scrollable) ─────────────────────────────────
        inst_box = QGroupBox("Simulation Instances")
        inst_box.setStyleSheet("""
            QGroupBox {
                color: #00ddff; border: 1px solid #2a4555;
                border-radius: 6px; margin-top: 8px; padding: 10px;
                font-weight: bold;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
        """)
        inst_outer = QVBoxLayout(inst_box)
        inst_outer.setContentsMargins(4, 4, 4, 4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(200)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch()

        scroll.setWidget(self._list_widget)
        inst_outer.addWidget(scroll)
        root.addWidget(inst_box)

        # ── Shared log ────────────────────────────────────────────────
        log_box = QGroupBox("Combined Simulation Log")
        log_box.setStyleSheet("""
            QGroupBox {
                color: #00ddff; border: 1px solid #2a4555;
                border-radius: 6px; margin-top: 8px; padding: 8px;
                font-weight: bold;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
        """)
        log_layout = QVBoxLayout(log_box)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumBlockCount(1000)
        self.log_output.setStyleSheet(
            "background: #05080a; color: #00ddff; "
            "font-family: 'Menlo', 'Consolas', monospace; font-size: 11px; border: none;"
        )

        btn_clear = QPushButton("Clear Log")
        btn_clear.setFixedHeight(24)
        btn_clear.setStyleSheet(
            "background: transparent; color: #92b0c3; border: 1px solid #2a4555; "
            "border-radius: 3px; font-size: 11px; padding: 0 10px;"
        )
        btn_clear.clicked.connect(self.log_output.clear)

        clr_row = QHBoxLayout()
        clr_row.addStretch()
        clr_row.addWidget(btn_clear)

        log_layout.addWidget(self.log_output)
        log_layout.addLayout(clr_row)
        root.addWidget(log_box, stretch=1)

    # ------------------------------------------------------------------ #
    def _add_instance(self):
        inst = SimInstance(
            instance_id=self._next_id,
            log_fn=self._append_log,
            on_remove=lambda: self._remove_instance(inst),
        )
        self._next_id += 1
        self._instances.append(inst)
        # Insert before the trailing stretch
        self._list_layout.insertWidget(self._list_layout.count() - 1, inst)

    def _remove_instance(self, inst: SimInstance):
        if inst.is_running():
            return  # shouldn't happen — remove btn disabled while running
        self._instances.remove(inst)
        self._list_layout.removeWidget(inst)
        inst.deleteLater()

    def _append_log(self, text: str):
        self.log_output.appendPlainText(text)
        sb = self.log_output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def stop_all(self):
        """Stop all running simulations — call this on GCS close."""
        for inst in self._instances:
            inst.stop_and_wait()
