from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QComboBox, QPushButton, QGroupBox, QScrollArea, QFrame, QLineEdit
from PySide6.QtCore import Qt, Signal

class VideoTab(QWidget):
    ai_settings_applied = Signal(str, str) # Atomic Engine config (engine, model) 🔐
    search_prompt_changed = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Scroll area for future-proofing advanced settings
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: #090e11; border: none; } ")
        
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setAlignment(Qt.AlignTop)
        
        # 1. AI Engine Section
        ai_box = QGroupBox("Reconnaissance AI Engine (YOLOv8)")
        ai_lay = QVBoxLayout(ai_box)
        
        lbl_ai_info = QLabel("Select the hardware acceleration provider for object tracking.\nCUDA natively requires an NVIDIA GPU and cu121 binaries.")
        lbl_ai_info.setStyleSheet("color: #557788; font-size: 11px;")
        ai_lay.addWidget(lbl_ai_info)
        
        ai_grid = QGridLayout()
        ai_grid.addWidget(QLabel("Hardware Provider:"), 0, 0)
        self.combo_ai_engine = QComboBox()
        self.combo_ai_engine.addItems(["CPU [Universal]", "CUDA [NVIDIA]", "DirectML [Windows GPU]", "OpenVINO [Intel]"])
        ai_grid.addWidget(self.combo_ai_engine, 0, 1)
        
        ai_grid.addWidget(QLabel("Detection Model:"), 1, 0)
        self.model_combo = QComboBox()
        self.model_combo.addItems(["RT-DETR v2"])
        # No auto‑apply; model changes are applied via the Apply button
        ai_grid.addWidget(self.model_combo, 1, 1)

        self.lbl_search_prompt = QLabel("Search Prompt:")
        self.txt_search_prompt = QLineEdit("person, car, truck, drone")
        self.txt_search_prompt.setPlaceholderText("Enter objects to search (comma separated)")
        self.txt_search_prompt.setStyleSheet("background-color: #111a22; color: #00ddff; padding: 4px; border: 1px solid #335566;")
        self.txt_search_prompt.textChanged.connect(self._emit_search_prompt)
        self.lbl_search_prompt.setVisible(False)
        self.txt_search_prompt.setVisible(False)
        
        ai_grid.addWidget(self.lbl_search_prompt, 2, 0)
        ai_grid.addWidget(self.txt_search_prompt, 2, 1)

        btn_apply_ai = QPushButton("Apply AI Engine Settings")
        btn_apply_ai.clicked.connect(self._emit_ai_engine)
        btn_apply_ai.setStyleSheet("background-color: rgba(0, 221, 255, 0.1); border: 1px solid #00ddff; color: #00ddff;")
        ai_grid.addWidget(btn_apply_ai, 3, 0, 1, 2) # Moved to row 3 to prevent overlap 🚀
        ai_lay.addLayout(ai_grid)
        
        container_layout.addWidget(ai_box)
        
        # 2. Advanced Visual Tuning
        vid_box = QGroupBox("Visual Stream Optimization")
        vid_lay = QVBoxLayout(vid_box)
        
        lbl_vid_info = QLabel("Configure internal buffering and decoding parameters for the FPV link.")
        lbl_vid_info.setStyleSheet("color: #557788; font-size: 11px;")
        vid_lay.addWidget(lbl_vid_info)
        
        vid_grid = QGridLayout()
        # Potential future settings like resolution scale, FPS limit, etc.
        vid_grid.addWidget(QLabel("Decryption / Codec:"), 0, 0)
        vid_grid.addWidget(QLabel("H.264 (Native)"), 0, 1)
        vid_lay.addLayout(vid_grid)
        
        container_layout.addWidget(vid_box)
        container_layout.addStretch()
        
        scroll.setWidget(container)
        layout.addWidget(scroll)
        
    def _emit_ai_engine(self):
        """Apply both engine and model settings atomically 🔐🚀"""
        engine = self.combo_ai_engine.currentText().split()[0]
        model_name = self.model_combo.currentText().split()[0]
        self.ai_settings_applied.emit(engine, model_name)
        
    def _emit_search_prompt(self):
        self.search_prompt_changed.emit(self.txt_search_prompt.text())

    def _handle_model_visibility(self, index):
        # No special UI for world prompts with RT‑DETR only
        self.lbl_search_prompt.setVisible(False)
        self.txt_search_prompt.setVisible(False)
