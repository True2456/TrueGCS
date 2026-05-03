from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox, QPushButton, QGroupBox, QScrollArea, QFrame, QLineEdit, QCheckBox, QSlider
from PySide6.QtCore import Qt, Signal

class VideoTab(QWidget):
    ai_settings_applied = Signal(str, str) # Atomic Engine config (engine, model) 🔐
    search_prompt_changed = Signal(str)
    labels_toggled = Signal(bool)
    box_color_changed = Signal(tuple)
    footprint_toggled = Signal(bool)  # Camera footprint toggle
    
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
        ai_box = QGroupBox("Reconnaissance AI Engine (YOLO26)")
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
        # Tactical mission-specific presets
        self.model_combo.addItems([
            "VisDrone-v2 (YOLO26s)",
            "YOLO26-1536px (High-Res)",
            "YOLO26-VisDrone (Legacy)",
            "RT-DETR v2"
        ])
        # No auto‑apply; model changes are applied via the Apply button
        self.model_combo.currentIndexChanged.connect(self._handle_model_visibility)
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

        self.btn_apply_ai = QPushButton("Apply AI Engine Settings")
        self.btn_apply_ai.clicked.connect(self._emit_ai_engine)
        self.btn_apply_ai.setStyleSheet("background-color: rgba(0, 221, 255, 0.1); border: 1px solid #00ddff; color: #00ddff;")
        ai_grid.addWidget(self.btn_apply_ai, 3, 0, 1, 2)
        ai_lay.addLayout(ai_grid)
        
        container_layout.addWidget(ai_box)
        
        # 1.5 Zarri Tactical AI Brain Config
        llm_box = QGroupBox("Zarri Tactical AI Brain Config")
        llm_grid = QGridLayout(llm_box)
        llm_grid.addWidget(QLabel("Server URL:"), 0, 0)
        self.txt_llm_url = QLineEdit("http://192.168.1.122:1234")
        self.txt_llm_url.setStyleSheet("background-color: #111a22; color: #00ddff; padding: 4px; border: 1px solid #2a4555;")
        llm_grid.addWidget(self.txt_llm_url, 0, 1)
        
        self.btn_llm_save = QPushButton("Apply / Refresh Models")
        self.btn_llm_save.setStyleSheet("background-color: rgba(0, 221, 255, 0.15); color: #00ddff; border: 1px solid #00ddff; padding: 4px 8px;")
        llm_grid.addWidget(self.btn_llm_save, 1, 0, 1, 2)
        
        self.chk_auto_connect = QCheckBox("Auto-Connect Local SITL (UDP 14550)")
        self.chk_auto_connect.setChecked(False)
        self.chk_auto_connect.setStyleSheet("color: #92b0c3; margin-top: 5px;")
        llm_grid.addWidget(self.chk_auto_connect, 2, 0, 1, 2)
        
        container_layout.addWidget(llm_box)
        
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
        
        vid_grid.addWidget(QLabel("Box HUD Color:"), 1, 0)
        self.combo_box_color = QComboBox()
        self.combo_box_color.addItem("Emerald Green", userData=(0, 255, 0))
        self.combo_box_color.addItem("Neon Blue", userData=(255, 221, 0))
        self.combo_box_color.addItem("Hot Pink", userData=(180, 105, 255))
        self.combo_box_color.addItem("Safety Orange", userData=(0, 165, 255))
        self.combo_box_color.addItem("Tactical White", userData=(255, 255, 255))
        self.combo_box_color.currentIndexChanged.connect(self._handle_color_change)
        vid_grid.addWidget(self.combo_box_color, 1, 1)

        self.chk_show_labels = QCheckBox("Show Labels & Confidence on HUD")
        self.chk_show_labels.setChecked(True)
        self.chk_show_labels.setStyleSheet("color: #00ddff; font-weight: bold;")
        self.chk_show_labels.toggled.connect(lambda state: self.labels_toggled.emit(state))
        vid_grid.addWidget(self.chk_show_labels, 2, 0, 1, 2)
        
        # Camera Footprint Toggle 📍
        self.chk_footprint = QCheckBox("Show Camera Footprint on Map")
        self.chk_footprint.setChecked(False)
        self.chk_footprint.setStyleSheet("color: #00ddff; font-weight: bold;")
        self.chk_footprint.toggled.connect(self._emit_footprint_toggle)
        vid_grid.addWidget(self.chk_footprint, 3, 0, 1, 2)
        
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
        text = self.model_combo.itemText(index)
        is_world = "World" in text
        # Only YOLO-World exposes the dynamic search prompt
        self.lbl_search_prompt.setVisible(is_world)
        self.txt_search_prompt.setVisible(is_world)

    def _handle_color_change(self, index):
        color_bgr = self.combo_box_color.currentData()
        self.box_color_changed.emit(color_bgr)

    def _emit_footprint_toggle(self, checked):
        """Emit footprint toggle signal."""
        self.footprint_toggled.emit(checked)
