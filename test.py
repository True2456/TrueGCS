import sys
import traceback
from PySide6.QtWidgets import QApplication
from ui.main_window import GCSMainWindow

def test():
    app = QApplication(sys.argv)
    window = GCSMainWindow()
    window.show()
    try:
        window.tab_ops.btn_vid_toggle.click()
    except Exception:
        traceback.print_exc()

if __name__ == "__main__":
    test()
