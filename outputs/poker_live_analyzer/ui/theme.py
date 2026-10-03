"""深藍桌面介面的共用樣式，保留清楚的文字與操作狀態。"""
STYLE='''
QWidget {background:#09151e;color:#dce8f2;font-family:"Inter","Noto Sans TC";font-size:15px;}
QMainWindow {background:#09151e;}
QWidget#surfacePanel {background:#101f2c;border:1px solid #263e50;border-radius:10px;}
QLabel#sectionTitle {background:transparent;color:#e4edf6;font-size:18px;font-weight:600;padding:4px;}
QPushButton {background:#192e43;border:1px solid #3b526b;border-radius:6px;padding:8px 14px;color:#e5eff7;font-weight:500;}
QPushButton:hover {background:#23425a;border-color:#4d8cad;}
QPushButton:pressed {background:#102536;}
QPushButton:disabled {color:#7790a3;}
QScrollArea {border:0;background:#09151e;}
QCheckBox {spacing:8px;color:#b9ccdb;}
QComboBox,QSpinBox,QDoubleSpinBox,QPlainTextEdit,QListWidget {background:#142737;border:1px solid #34516a;border-radius:5px;padding:5px;color:#e5eff7;}
QTabWidget::pane {border:1px solid #34516a;}
QTabBar::tab {background:#142737;padding:9px 14px;color:#aebfce;}
QTabBar::tab:selected {background:#244259;color:#ffffff;}
QTableWidget {background:#122332;alternate-background-color:#183047;color:#dce8f2;gridline-color:#2c4357;}
QHeaderView::section {background:#1b3349;color:#dce8f2;border:0;padding:8px;}
QStatusBar {color:#92adbf;font-size:12px;}
QScrollBar:vertical {background:#101f2d;width:8px;}
QScrollBar::handle:vertical {background:#34516a;border-radius:4px;min-height:25px;}
'''

def accent(color):
    return {'#087d55':'#43dfb9','#7045b4':'#bf8aff','#c42b36':'#ff7d8b',
        '#1765aa':'#7ebaff','#9a6500':'#f5bf67'}.get(color,color)
