from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
                             QPushButton, QLineEdit, QComboBox, QScrollArea, QFrame, 
                             QTabWidget, QProgressBar, QGroupBox, QTableWidget, 
                             QTableWidgetItem, QHeaderView)
from PySide6.QtCore import Qt, Signal, QThread
from core.tile_cache import TileCacheDownloader, NSW_BOUNDS
from core.param_metadata import ParamMetadataProvider
from ui.widgets.param_widgets import EnumSelector, BitmaskSelector

from PySide6.QtCore import Qt, Signal, QThread

class TileDownloadThread(QThread):
    progress = Signal(int, int) # Current, Total
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.downloader = TileCacheDownloader()
        self.downloader.zoom_range = (6, 12) # Reasonable default for NSW chunk

    def run(self):
        def callback(curr, total, z, failed):
            self.progress.emit(curr, total)
        
        self.downloader.download_region(progress_callback=callback)
        self.finished.emit()

class CfgTab(QWidget):
    fetch_params_requested = Signal(list)
    fetch_full_list_requested = Signal()
    write_param_requested = Signal(str, float)
    
    # Local controller signals
    pitch_gains_changed = Signal(float, float, float)
    yaw_gains_changed = Signal(float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.param_inputs = {}
        self.is_fetching_full = False
        self.metadata = ParamMetadataProvider()
        # Connect to metadata load to upgrade widgets if they were plain QLineEdits
        self.metadata.loaded.connect(self.upgrade_all_widgets)
        
        self.lbl_status = None # Assigned by external controller if needed
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        top_bar = QHBoxLayout()
        btn_refresh = QPushButton("Sync Curated")
        btn_refresh.setFixedWidth(150)
        btn_refresh.clicked.connect(self.request_curated_params)
        top_bar.addWidget(btn_refresh)
        
        self.param_progress = QProgressBar()
        self.param_progress.setFormat("Params: %v/%m")
        self.param_progress.setStyleSheet("QProgressBar { border: 1px solid #2a4555; background: #090e11; color: #00ddff; text-align: center; } QProgressBar::chunk { background-color: #00ddff; }")
        self.param_progress.hide()
        top_bar.addWidget(self.param_progress)
        
        top_bar.addStretch()
        layout.addLayout(top_bar)
        
        # Create Sub-Tabs
        self.cfg_tabs = QTabWidget()
        layout.addWidget(self.cfg_tabs)
        
        # 1. VTOL Tab
        tab_vtol = QWidget()
        v_lay = QGridLayout(tab_vtol)
        v_lay.setAlignment(Qt.AlignTop)
        self.add_param_ui(v_lay, "Q_ENABLE", 0, "Enable QuadPlane (1=Yes)")
        self.add_param_ui(v_lay, "Q_FRAME_CLASS", 1, "Tailsitter Class")
        self.add_param_ui(v_lay, "Q_FRAME_TYPE", 2, "Tailsitter Type")
        self.add_param_ui(v_lay, "Q_TAILSIT_ANGLE", 3, "Transition Angle (deg)")
        self.add_param_ui(v_lay, "Q_TRANSITION_MS", 4, "Transition Time (ms)")
        self.add_param_ui(v_lay, "Q_RTL_MODE", 5, "Return to Launch Mode")
        self.add_param_ui(v_lay, "Q_TAILSIT_MOTMX", 6, "Tailsitter Max Motor")
        self.add_param_ui(v_lay, "Q_TAILSIT_GSCMSK", 7, "Gain Scaling Mask")
        self.add_param_ui(v_lay, "Q_M_SPIN_MIN", 8, "Motor Spin Min")
        self.add_param_ui(v_lay, "Q_M_SPIN_MAX", 9, "Motor Spin Max")
        
        # 1.5 VTOL PID Tuning Tab
        tab_pid = QWidget()
        p_lay = QGridLayout(tab_pid)
        p_lay.setAlignment(Qt.AlignTop)
        self.add_param_ui(p_lay, "Q_A_RAT_PIT_P", 0, "Pitch Rate P")
        self.add_param_ui(p_lay, "Q_A_RAT_PIT_I", 1, "Pitch Rate I")
        self.add_param_ui(p_lay, "Q_A_RAT_PIT_D", 2, "Pitch Rate D")
        self.add_param_ui(p_lay, "Q_A_RAT_RLL_P", 3, "Roll Rate P")
        self.add_param_ui(p_lay, "Q_A_RAT_RLL_I", 4, "Roll Rate I")
        self.add_param_ui(p_lay, "Q_A_RAT_RLL_D", 5, "Roll Rate D")
        self.add_param_ui(p_lay, "Q_A_RAT_YAW_P", 6, "Yaw Rate P")

        # 2. Gimbal Tab
        tab_gimbal = QWidget()
        g_lay = QGridLayout(tab_gimbal)
        g_lay.setAlignment(Qt.AlignTop)
        self.add_param_ui(g_lay, "MNT1_TYPE", 0, "Mount Type (Mavlink=4)")
        self.add_param_ui(g_lay, "MNT1_PITCH_MIN", 1, "Pitch Min (deg)")
        self.add_param_ui(g_lay, "MNT1_PITCH_MAX", 2, "Pitch Max (deg)")
        self.add_param_ui(g_lay, "MNT1_YAW_MIN", 3, "Yaw Min (deg)")
        self.add_param_ui(g_lay, "MNT1_YAW_MAX", 4, "Yaw Max (deg)")
        self.add_param_ui(g_lay, "MNT1_RC_IN_TILT", 5, "RC Input Tilt")
        self.add_param_ui(g_lay, "MNT1_RC_IN_PAN", 6, "RC Input Pan")

        # 3. Serial Tab
        tab_serial = QWidget()
        s_lay = QGridLayout(tab_serial)
        s_lay.setAlignment(Qt.AlignTop)
        self.add_param_ui(s_lay, "SERIAL1_PROTOCOL", 0, "Telemetry 1 Protocol")
        self.add_param_ui(s_lay, "SERIAL1_BAUD", 1, "Telemetry 1 Baud")
        self.add_param_ui(s_lay, "SERIAL2_PROTOCOL", 2, "Telemetry 2 Protocol")
        self.add_param_ui(s_lay, "SERIAL2_BAUD", 3, "Telemetry 2 Baud")
        
        # 4. Failsafes Tab
        tab_fs = QWidget()
        f_lay = QGridLayout(tab_fs)
        f_lay.setAlignment(Qt.AlignTop)
        self.add_param_ui(f_lay, "BATT_FS_VOLTSRC", 0, "Battery Voltage Source")
        self.add_param_ui(f_lay, "BATT_CRT_VOLT", 1, "Critical Voltage")
        self.add_param_ui(f_lay, "BATT_FS_LOW_ACT", 2, "Low Action")
        self.add_param_ui(f_lay, "FS_GCS_ENABL", 3, "GCS Failsafe Enable")
        self.add_param_ui(f_lay, "FS_LONG_ACTN", 4, "Long Failsafe Action")

        # 5. Map Tools Tab
        tab_map = QWidget()
        m_lay = QVBoxLayout(tab_map)
        m_lay.setAlignment(Qt.AlignTop)
        
        m_lay.addWidget(QLabel("OFFLINE MAP MANAGEMENT"))
        lbl_info = QLabel("Download satellite tiles for NSW, Australia (Zoom 6-12) for offline use.")
        lbl_info.setStyleSheet("color: #557788; font-size: 11px;")
        m_lay.addWidget(lbl_info)
        
        self.btn_download_map = QPushButton("Pre-download NSW Tiles (~2GB)")
        self.btn_download_map.clicked.connect(self.start_map_download)
        m_lay.addWidget(self.btn_download_map)
        
        self.map_progress = QProgressBar()
        self.map_progress.setStyleSheet("QProgressBar { border: 1px solid #2a4555; background: #090e11; color: #00ddff; text-align: center; } QProgressBar::chunk { background-color: #00ddff; }")
        self.map_progress.hide()
        m_lay.addWidget(self.map_progress)

        # 6. Gimbal Tuning Tab
        tab_gt = QWidget()
        gt_lay = QVBoxLayout(tab_gt)
        gt_lay.setAlignment(Qt.AlignTop)
        
        # Pitch Section
        p_box = QGroupBox("Pitch Tracking (PID)")
        p_grid = QGridLayout(p_box)
        self.txt_p_kp = QLineEdit("0.5"); p_grid.addWidget(QLabel("P:"), 0, 0); p_grid.addWidget(self.txt_p_kp, 0, 1)
        self.txt_p_ki = QLineEdit("0.01"); p_grid.addWidget(QLabel("I:"), 0, 2); p_grid.addWidget(self.txt_p_ki, 0, 3)
        self.txt_p_kd = QLineEdit("0.1"); p_grid.addWidget(QLabel("D:"), 0, 4); p_grid.addWidget(self.txt_p_kd, 0, 5)
        btn_update_p = QPushButton("Update Pitch Gains")
        btn_update_p.clicked.connect(self._emit_pitch_gains)
        p_grid.addWidget(btn_update_p, 1, 0, 1, 6)
        gt_lay.addWidget(p_box)
        
        # Yaw Section
        y_box = QGroupBox("Yaw Tracking (PID)")
        y_grid = QGridLayout(y_box)
        self.txt_y_kp = QLineEdit("0.5"); y_grid.addWidget(QLabel("P:"), 0, 0); y_grid.addWidget(self.txt_y_kp, 0, 1)
        self.txt_y_ki = QLineEdit("0.01"); y_grid.addWidget(QLabel("I:"), 0, 2); y_grid.addWidget(self.txt_y_ki, 0, 3)
        self.txt_y_kd = QLineEdit("0.1"); y_grid.addWidget(QLabel("D:"), 0, 4); y_grid.addWidget(self.txt_y_kd, 0, 5)
        btn_update_y = QPushButton("Update Yaw Gains")
        btn_update_y.clicked.connect(self._emit_yaw_gains)
        y_grid.addWidget(btn_update_y, 1, 0, 1, 6)
        gt_lay.addWidget(y_box)
        
        self.cfg_tabs.addTab(self.wrap_in_scroll(tab_vtol), "VTOL / Tailsitter")
        self.cfg_tabs.addTab(self.wrap_in_scroll(tab_pid), "VTOL PID Tuning")
        self.cfg_tabs.addTab(self.wrap_in_scroll(tab_gimbal), "Gimbal & Payload")
        self.cfg_tabs.addTab(self.wrap_in_scroll(tab_serial), "Serial Defaults")
        self.cfg_tabs.addTab(self.wrap_in_scroll(tab_fs), "Failsafes & Safety")
        self.cfg_tabs.addTab(self.wrap_in_scroll(tab_map), "Map Tools")
        self.cfg_tabs.addTab(self.wrap_in_scroll(tab_gt), "Gimbal Tuning")
        
        # AI Engine settings relocated to VideoTab
        
        # 7. Advanced / Full List Tab
        tab_adv = QWidget()
        adv_lay = QVBoxLayout(tab_adv)
        
        search_lay = QHBoxLayout()
        search_lay.addWidget(QLabel("SEARCH/FETCH:"))
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Exact ID + Enter to fetch, or type to filter list")
        self.txt_search.textChanged.connect(self.filter_advanced_table)
        self.txt_search.returnPressed.connect(self.search_and_fetch_remote)
        search_lay.addWidget(self.txt_search)
        
        btn_fetch_all = QPushButton("Download Entire Drone Parameter List")
        btn_fetch_all.clicked.connect(self.request_all_params_list)
        search_lay.addWidget(btn_fetch_all)
        
        adv_lay.addLayout(search_lay)
        
        self.table_params = QTableWidget(0, 4)
        self.table_params.setHorizontalHeaderLabels(["Parameter", "Value", "Description", "Action"])
        self.table_params.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_params.setStyleSheet("QTableWidget { background-color: #090e11; gridline-color: #1a2a35; } "
                                        "QHeaderView::section { background-color: #111a22; color: #00ddff; border: 1px solid #2a4555; }")
        adv_lay.addWidget(self.table_params)
        
        self.cfg_tabs.addTab(tab_adv, "Advanced / Full List")

    def wrap_in_scroll(self, widget):
        """Wraps a widget in a QScrollArea with consistent dark-themed styling."""
        widget.setObjectName("ParamTabContent")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        # Background must be forced on the viewport too
        scroll.setStyleSheet("QScrollArea { background-color: #090e11; border: none; } "
                             "QScrollBar:vertical { background: #090e11; width: 10px; } "
                             "QScrollBar::handle:vertical { background: #2a4555; min-height: 20px; }")
        scroll.setWidget(widget)
        return scroll

    def _emit_pitch_gains(self):
        try:
            p = float(self.txt_p_kp.text())
            i = float(self.txt_p_ki.text())
            d = float(self.txt_p_kd.text())
            self.pitch_gains_changed.emit(p, i, d)
        except ValueError: pass

    def _emit_yaw_gains(self):
        try:
            p = float(self.txt_y_kp.text())
            i = float(self.txt_y_ki.text())
            d = float(self.txt_y_kd.text())
            self.yaw_gains_changed.emit(p, i, d)
        except ValueError: pass

    # def _emit_ai_engine(self):
    #     engine = self.combo_ai_engine.currentText().split()[0]
    #     self.ai_engine_changed.emit(engine)
        
    def start_map_download(self):
        self.btn_download_map.setEnabled(False)
        self.map_progress.show()
        self.dl_thread = TileDownloadThread()
        self.dl_thread.progress.connect(self.update_map_progress)
        self.dl_thread.finished.connect(self.map_download_finished)
        self.dl_thread.start()

    def update_map_progress(self, curr, total):
        self.map_progress.setMaximum(total)
        self.map_progress.setValue(curr)

    def map_download_finished(self):
        self.btn_download_map.setEnabled(True)
        self.btn_download_map.setText("NSW Tiles Synced")
        if self.lbl_status:
            self.lbl_status.setText("System: Offline map cache complete.")

    def request_curated_params(self):
        self.param_progress.hide()
        param_names = list(self.param_inputs.keys())
        self.fetch_params_requested.emit(param_names)

    def request_all_params_list(self):
        self.is_fetching_full = True
        self.param_progress.show()
        self.param_progress.setValue(0)
        self.fetch_full_list_requested.emit()

    def search_and_fetch_remote(self):
        txt = self.txt_search.text().upper().strip()
        if txt:
            self.fetch_params_requested.emit([txt])

    def update_param_progress(self, current, total):
        # Only show/manage progress bar if we explicitly requested the full drone list
        if not self.is_fetching_full: return
        
        if self.param_progress.isHidden(): self.param_progress.show()
        self.param_progress.setMaximum(total)
        self.param_progress.setValue(current)
        if current >= total and total > 0:
            self.param_progress.hide()
            self.is_fetching_full = False

    def add_param_ui(self, layout, param_name, row, desc):
        layout.addWidget(QLabel(f"{param_name}:"), row, 0)
        
        # Meta-aware widget selection
        info = self.metadata.get_param_info(param_name)
        inp = None
        
        if info and "Values" in info:
            inp = EnumSelector(info["Values"])
            print(f"Using EnumSelector for {param_name}")
        elif info and "Bitmask" in info:
            inp = BitmaskSelector(info["Bitmask"])
            print(f"Using BitmaskSelector for {param_name}")
        else:
            inp = QLineEdit()
            inp.setFixedWidth(100)

        self.param_inputs[param_name] = inp
        layout.addWidget(inp, row, 1)
        
        # Priority: Metadata description > Local placeholder
        final_desc = info.get("Description", desc) if info else desc
        lbl_desc = QLabel(f"// {final_desc}")
        lbl_desc.setWordWrap(True)
        lbl_desc.setMaximumWidth(400)
        lbl_desc.setStyleSheet("color: #557788; font-weight: normal; font-size: 10px;")
        layout.addWidget(lbl_desc, row, 2)
        
        btn = QPushButton("Write")
        btn.setFixedWidth(80)
        btn.clicked.connect(lambda checked, p=param_name: self.write_param(p))
        layout.addWidget(btn, row, 3)

    def write_param(self, param_name):
        try:
            inp = self.param_inputs[param_name]
            if hasattr(inp, "get_value"):
                val = inp.get_value()
            else:
                val = float(inp.text())
            
            self.write_param_requested.emit(param_name, val)
        except ValueError:
            if self.lbl_status:
                self.lbl_status.setText(f"System: Invalid value for {param_name}")

    def filter_advanced_table(self, text):
        """Filters the advanced table rows based on search text."""
        text = text.upper()
        for i in range(self.table_params.rowCount()):
            param_id = self.table_params.item(i, 0).text()
            self.table_params.setRowHidden(i, text not in param_id)

    def update_param_value(self, param_id, value):
        # 1. Update curated inputs
        if param_id in self.param_inputs:
            inp = self.param_inputs[param_id]
            if hasattr(inp, "set_value"):
                inp.set_value(value)
            elif isinstance(inp, QLineEdit):
                # Clean rounding to 2 decimal places for readability
                clean_val = f"{value:.2f}".rstrip('0').rstrip('.')
                inp.setText(clean_val)
        
        # 2. Update full table (Search logic)
        self.update_advanced_table_row(param_id, value)

    def update_advanced_table_row(self, param_id, value):
        """Finds or creates a row in the full parameter table."""
        # Clean rounding to 2 decimal places for readability
        clean_val = f"{value:.2f}".rstrip('0').rstrip('.')
        
        # Search for existing row
        items = self.table_params.findItems(param_id, Qt.MatchExactly)
        if items:
            row = items[0].row()
            self.table_params.item(row, 1).setText(clean_val)
        else:
            # Create new row
            row = self.table_params.rowCount()
            self.table_params.insertRow(row)
            
            # Param name (Column 0)
            item_id = QTableWidgetItem(param_id)
            item_id.setFlags(item_id.flags() & ~Qt.ItemIsEditable)
            self.table_params.setItem(row, 0, item_id)
            
            # Value (Column 1)
            item_val = QTableWidgetItem(clean_val)
            self.table_params.setItem(row, 1, item_val)
            
            # Description (Column 2)
            info = self.metadata.get_param_info(param_id)
            desc = info.get("Description", "") if info else ""
            item_desc = QTableWidgetItem(desc)
            item_desc.setFlags(item_desc.flags() & ~Qt.ItemIsEditable)
            item_desc.setToolTip(desc)
            self.table_params.setItem(row, 2, item_desc)
            
            # Action (Column 3)
            btn = QPushButton("Write")
            btn.setFixedWidth(60)
            btn.clicked.connect(lambda checked, p=param_id, r=row: self.write_param_from_table(p, r))
            self.table_params.setCellWidget(row, 3, btn)

    def write_param_from_table(self, param_name, row):
        try:
            val_txt = self.table_params.item(row, 1).text()
            val = float(val_txt)
            self.write_param_requested.emit(param_name, val)
        except ValueError:
            if self.lbl_status:
                self.lbl_status.setText(f"System: Invalid value for {param_name}")

    def upgrade_all_widgets(self):
        """Called once metadata is downloaded to upgrade QLineEdits to selectors."""
        print("CfgTab: Metadata loaded, upgrading widgets...")
        for param_name, old_inp in list(self.param_inputs.items()):
            if isinstance(old_inp, QLineEdit):
                info = self.metadata.get_param_info(param_name)
                if info and ("Values" in info or "Bitmask" in info):
                    print(f"  Upgrading {param_name}...")
                    # Get layout and position
                    layout = old_inp.parentWidget().layout()
                    if not isinstance(layout, QGridLayout): continue
                    
                    idx = layout.indexOf(old_inp)
                    row, col, _, _ = layout.getItemPosition(idx)
                    
                    # Create new
                    new_inp = None
                    if "Values" in info:
                        new_inp = EnumSelector(info["Values"])
                    else:
                        new_inp = BitmaskSelector(info["Bitmask"])
                    
                    # Swap
                    layout.removeWidget(old_inp)
                    
                    # Capture existing value before deletion!
                    current_txt = old_inp.text()
                    old_inp.deleteLater()
                    
                    layout.addWidget(new_inp, row, col)
                    self.param_inputs[param_name] = new_inp
                    
                    # Restore value if it was valid
                    if current_txt:
                        try:
                            val = float(current_txt)
                            new_inp.set_value(val)
                        except: pass
                    
                    # Update description if it was basic
                    desc_item = layout.itemAtPosition(row, 2)
                    if desc_item and desc_item.widget():
                        desc_item.widget().setText(f"// {info.get('Description', '')}")
