from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                             QComboBox, QMenu, QWidgetAction, QCheckBox, QFrame)
from PySide6.QtCore import Qt, Signal

class EnumSelector(QComboBox):
    """Maps human-readable names from ArduPilot to integer values."""
    def __init__(self, values_dict, parent=None):
        super().__init__(parent)
        self.val_map = {} # Code -> Label
        self.code_map = {} # Label -> Code (as string)
        
        # Ensure values are sorted by float key (handles '0', '1.0', etc.)
        try:
            sorted_keys = sorted(values_dict.keys(), key=lambda x: float(x))
        except:
            sorted_keys = sorted(values_dict.keys())

        for k in sorted_keys:
            v = values_dict[k]
            self.addItem(v)
            # Store keys normalized by int if possible
            try: k_norm = str(int(float(k)))
            except: k_norm = k
            self.val_map[k_norm] = v
            self.code_map[v] = k_norm
    
    def get_value(self):
        label = self.currentText()
        try:
            return float(self.code_map.get(label, 0))
        except: return 0.0

    def set_value(self, value):
        val_str = str(int(value))
        if val_str in self.val_map:
            self.setCurrentText(self.val_map[val_str])

class BitmaskSelector(QPushButton):
    """A multi-select check-list for ArduPilot bitmask parameters."""
    value_changed = Signal(float)

    def __init__(self, bit_dict, parent=None):
        super().__init__("Select Bits...", parent)
        self.bit_dict = bit_dict # bit_index -> Label
        self.active_value = 0.0
        self.setFixedWidth(140)
        
        self.menu = QMenu(self)
        self.menu.setStyleSheet("QMenu { background-color: #111a22; border: 1px solid #2a4555; padding: 5px; }")
        self.checkboxes = {}
        
        # Container widget for checkboxes
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)
        
        try:
            sorted_bits = sorted(bit_dict.keys(), key=lambda x: float(x))
        except:
            sorted_bits = sorted(bit_dict.keys())

        for bit in sorted_bits:
            label = bit_dict[bit]
            cb = QCheckBox(f"{bit}: {label}")
            cb.setStyleSheet("color: #00ddff; font-size: 11px;")
            cb.toggled.connect(lambda checked, b=bit: self._on_bit_toggled(b, checked))
            layout.addWidget(cb)
            self.checkboxes[bit] = cb

        # Wrap in QWidgetAction to embed in QMenu
        wa = QWidgetAction(self.menu)
        wa.setDefaultWidget(container)
        self.menu.addAction(wa)

        self.clicked.connect(self._show_menu)

    def _show_menu(self):
        self.menu.exec(self.mapToGlobal(self.rect().bottomLeft()))

    def _on_bit_toggled(self, bit, checked):
        val = 2 ** int(bit)
        if checked:
            # Avoid duplicate addition if already set
            if not (int(self.active_value) & val):
                self.active_value += val
        else:
            if (int(self.active_value) & val):
                self.active_value -= val
        
        self._update_text()
        self.value_changed.emit(self.active_value)

    def _update_text(self):
        enabled = []
        for bit, cb in self.checkboxes.items():
            if cb.isChecked():
                enabled.append(bit)
        
        if not enabled:
            self.setText("None Set")
        else:
            self.setText("Bits: " + ", ".join(enabled[:2]) + ("..." if len(enabled) > 2 else ""))

    def get_value(self):
        return self.active_value

    def set_value(self, value):
        self.active_value = float(value)
        ival = int(value)
        # Block signals to prevent recursion during batch update
        for bit, cb in self.checkboxes.items():
            cb.blockSignals(True)
            bit_val = 2 ** int(bit)
            cb.setChecked(bool(ival & bit_val))
            cb.blockSignals(False)
        self._update_text()
