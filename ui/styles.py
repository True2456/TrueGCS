# Keeping the sleek dark BF3 theme but applying professional labels
BF3_STYLE = """
QMainWindow {
    background-color: #090e11;
}
QWidget {
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
    color: #92b0c3;
    background-color: transparent;
}
QMainWindow, QDialog, QScrollArea, #ParamTabContent {
    background-color: #090e11;
}
QLabel {
    color: #00ddff;
    font-weight: bold;
}
QLabel#DataLabel {
    color: #ffffff;
    font-weight: normal;
}
QPushButton {
    background-color: rgba(0, 221, 255, 0.1);
    border: 1px solid #00ddff;
    color: #00ddff;
    padding: 6px 15px;
    font-weight: bold;
    text-transform: uppercase;
}
QPushButton:hover {
    background-color: rgba(0, 221, 255, 0.3);
}
QPushButton:pressed {
    background-color: #00ddff;
    color: #090e11;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: rgba(255, 255, 255, 0.05);
    border: 1px solid #2a4555;
    color: #ffffff;
    padding: 4px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #00ddff;
}
QComboBox QAbstractItemView {
    background-color: #111a22;
    border: 1px solid #2a4555;
    color: #ffffff;
    selection-background-color: rgba(0, 221, 255, 0.3);
}
QMenu {
    background-color: #111a22;
    border: 1px solid #2a4555;
    color: #ffffff;
    padding: 5px;
}
QMenu::item:selected {
    background-color: rgba(0, 221, 255, 0.3);
}
QCheckBox::indicator {
    border: 1px solid #2a4555;
    width: 14px;
    height: 14px;
    background-color: #090e11;
}
QCheckBox::indicator:checked {
    background-color: #00ddff;
}
QTabWidget::pane {
    border: 1px solid #00ddff;
    background-color: #090e11;
}
QTabBar::tab {
    background-color: #111a22;
    color: #557788;
    padding: 10px 30px;
    border: 1px solid #2a4555;
    border-bottom: none;
    font-weight: bold;
    font-size: 14px;
}
QTabBar::tab:selected {
    background-color: rgba(0, 221, 255, 0.15);
    color: #00ddff;
    border: 1px solid #00ddff;
    border-bottom: none;
}
QGroupBox {
    border: 1px solid #2a4555;
    margin-top: 15px;
    font-weight: bold;
    color: #00ddff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 5px;
}
QWebEngineView {
    background-color: #090e11;
    border: none;
}
QGroupBox#MapGroupBox {
    border: 1px solid rgba(0, 221, 255, 0.35);
    background-color: #060a0d;
}
QGroupBox#MapGroupBox::title {
    color: #00ddff;
    font-size: 12px;
    letter-spacing: 1px;
}
"""
