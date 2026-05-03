from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QLineEdit, QComboBox, QLabel, QFrame
from PySide6.QtCore import Qt, Signal

class AIPanel(QFrame):
    # Signals to emit up to main.py
    prompt_submitted = Signal(str, str) # prompt, model_name
    models_refresh_requested = Signal(str) # Now passes the URL to fetch from
    close_requested = Signal() # Emitted when the user clicks the close button

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setObjectName("aiPanel")
        self.setStyleSheet("""
            #aiPanel {
                background-color: rgba(9, 21, 28, 0.96);
                border: 1px solid rgba(0, 221, 255, 0.35);
                border-radius: 10px;
            }
        """)
        self.setFixedWidth(450)
        self.setMinimumHeight(500)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header (Matching Mission Planner)
        header_widget = QWidget()
        header_widget.setStyleSheet("""
            background-color: rgba(0, 221, 255, 0.1); 
            border-bottom: 1px solid rgba(0, 221, 255, 0.2);
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
        """)
        header_lay = QHBoxLayout(header_widget)
        header_lay.setContentsMargins(12, 12, 12, 12)
        
        header_lbl = QLabel("TACTICAL AI")
        header_lbl.setStyleSheet("color: #00ddff; font-weight: bold; font-size: 13px; letter-spacing: 1px; border: none; background: transparent;")
        
        self.btn_close = QPushButton("✕")
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.setStyleSheet("background-color: transparent; color: #ff3232; font-weight: bold; border: none; font-size: 14px; padding: 0px 5px;")
        self.btn_close.clicked.connect(self.close_requested.emit)
        
        header_lay.addWidget(header_lbl)
        header_lay.addStretch()
        header_lay.addWidget(self.btn_close)
        main_layout.addWidget(header_widget)
        
        # Body Layout
        body_lay = QVBoxLayout()
        body_lay.setContentsMargins(10, 10, 10, 10)
        body_lay.setSpacing(10)
        
        # Top Bar: Model Selection
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("LM Studio Model:", styleSheet="color: #92b0c3; border: none; background: transparent;"))
        self.combo_model = QComboBox()
        self.combo_model.setStyleSheet("background-color: #060c11; color: #00ddff; font-weight: bold; border: 1px solid rgba(0, 221, 255, 0.2); border-radius: 2px;")
        top_bar.addWidget(self.combo_model, stretch=1)
        
        self.btn_refresh = QPushButton("Connect / Refresh")
        self.btn_refresh.setStyleSheet("background-color: rgba(0, 221, 255, 0.15); color: #00ddff; border: 1px solid rgba(0, 221, 255, 0.3); padding: 4px 8px; border-radius: 2px;")
        self.btn_refresh.clicked.connect(self.request_refresh)
        top_bar.addWidget(self.btn_refresh)
        
        body_lay.addLayout(top_bar)

        # Main Chat Area
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("background-color: rgba(255, 255, 255, 0.03); color: #a1b0b8; font-size: 14px; border: 1px solid rgba(146, 176, 195, 0.15); border-radius: 6px; padding: 5px;")
        body_lay.addWidget(self.chat_display)

        # Command Preview Box
        self.command_preview = QTextEdit()
        self.command_preview.setReadOnly(True)
        self.command_preview.setMaximumHeight(150)
        self.command_preview.setStyleSheet("background-color: #05080a; color: #00ff00; font-family: monospace; border: 1px solid rgba(146, 176, 195, 0.15); border-radius: 6px; padding: 5px;")
        self.command_preview.setPlaceholderText("LLM Command Output Preview...")
        body_lay.addWidget(self.command_preview)

        # Input Area
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("'Takeoff to 40m'  |  /identify  |  /locate the red car")
        self.input_field.setStyleSheet("background: #060c11; color: #00ddff; border: 1px solid rgba(0, 221, 255, 0.2); padding: 8px; font-size: 14px; border-radius: 4px;")
        self.input_field.returnPressed.connect(self.submit_prompt)
        input_layout.addWidget(self.input_field)

        self.btn_send = QPushButton("EXECUTE (AI)")
        self.btn_send.setStyleSheet("background-color: rgba(0, 221, 255, 0.15); border: 1px solid #00ddff; color: #00ddff; font-weight: bold; padding: 8px 15px; border-radius: 4px;")
        self.btn_send.clicked.connect(self.submit_prompt)
        input_layout.addWidget(self.btn_send)
        
        body_lay.addLayout(input_layout)
        main_layout.addLayout(body_lay)

    def request_refresh(self):
        # We emit without the URL, main.py will grab it from tabs_cfg
        self.models_refresh_requested.emit("")

    def submit_prompt(self):
        prompt = self.input_field.text().strip()
        model = self.combo_model.currentText()
        if prompt and model:
            self.append_chat(f"<b>[PILOT]</b> {prompt}", "#00ddff")
            self.prompt_submitted.emit(prompt, model)
            self.input_field.clear()
            self.btn_send.setEnabled(False) # Disable until response
            self.input_field.setEnabled(False)
            self.append_chat("<i>[AI] Analyzing request and generating commands...</i>", "#556b7a")

    def append_chat(self, text, color="#a1b0b8"):
        self.chat_display.append(f"<span style='color:{color};'>{text}</span>")

    def show_preview(self, json_str):
        self.command_preview.setPlainText(json_str)

    def unlock_input(self):
        self.btn_send.setEnabled(True)
        self.input_field.setEnabled(True)
        self.input_field.setFocus()

    def update_models(self, models):
        current = self.combo_model.currentText()
        self.combo_model.clear()
        self.combo_model.addItems(models)
        if current in models:
            self.combo_model.setCurrentText(current)
