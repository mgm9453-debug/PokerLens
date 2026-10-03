"""獨立開啟相同的設定視窗。"""
import sys
from PySide6.QtWidgets import QApplication
from control_settings import read,write,validate
from ui.control_dialog import ControlDialog

def create_window():
    try: options=read()
    except (OSError,ValueError): options=validate({})
    window=ControlDialog(options,write,lambda:'獨立設定控制台｜分析器開啟時會每秒載入新設定。')
    return window

if __name__=='__main__':
    app=QApplication(sys.argv)
    app.setStyle('Fusion')
    window=create_window()
    window.show()
    raise SystemExit(app.exec())
