# 主要配色集中於此，僅影響介面呈現。
COLORS = {'background':'#08090A','card':'#151617','secondary':'#1B1C1E',
          'gold':'#D8AE62','text_gold':'#F4DCA4','border':'#49433A',
          'text':'#FFFFFF','muted':'#FFFFFF','win':'#F0CE81','tie':'#D8A3E8',
          'matrix':'#0B9F68','winner':'#C94D4D'}

"""黑金桌面介面的共用樣式，保留清楚的文字與操作狀態。"""
STYLE='''
QWidget {background:#0D0C0A;color:#F2EEE5;font-family:"Inter","GenSenRounded2 TW","Noto Sans TC";font-size:15px;}
QMainWindow {background:#0D0C0A;}
QWidget#surfacePanel {background:#15120F;border:1px solid #9B7133;border-radius:16px;}
QLabel#sectionTitle {background:transparent;color:#E8CA8A;font-size:18px;font-weight:600;padding:4px;}
QPushButton {background:#15120F;border:1px solid #9B7133;border-radius:10px;padding:8px 14px;color:#F2EEE5;font-weight:400;}
QPushButton:hover {background:#292016;border-color:#D8AE62;}
QPushButton:pressed {background:#1C1712;}
QPushButton:disabled {color:#746D61;}
QScrollArea {border:0;background:#0D0C0A;}
QCheckBox {spacing:8px;color:#B9B3AA;}
QComboBox,QSpinBox,QDoubleSpinBox,QPlainTextEdit,QListWidget {background:#1C1712;border:1px solid #71552C;border-radius:5px;padding:5px;color:#E8CA8A;}
QTabWidget::pane {border:1px solid #71552C;}
QTabBar::tab {background:#1C1712;padding:9px 14px;color:#B9B3AA;}
QTabBar::tab:selected {background:#302619;color:#ffffff;}
QTableWidget {background:#15120F;alternate-background-color:#1C1712;color:#F2EEE5;gridline-color:#71552C;}
QHeaderView::section {background:#1C1712;color:#F2EEE5;border:0;padding:8px;}
QStatusBar {color:#B9B3AA;font-size:12px;}
QScrollBar:vertical {background:#15120F;width:8px;}
QScrollBar::handle:vertical {background:#71552C;border-radius:4px;min-height:25px;}
'''

# 主題表使用同一配色來源。
for key in ('background','card','secondary','gold','text_gold','border','text','muted'):
    STYLE=STYLE.replace({'background':'#0D0C0A','card':'#15120F','secondary':'#1C1712',
                         'gold':'#D8AE62','text_gold':'#E8CA8A','border':'#9B7133',
                         'text':'#F2EEE5','muted':'#B9B3AA'}[key],COLORS[key])

def accent(color):
    return {'#087d55':'#8DDCB5','#7045b4':COLORS['tie'],'#c42b36':'#FFAAAA',
        '#1765aa':COLORS['text_gold'],'#9a6500':COLORS['text_gold']}.get(color,color)


def card_style(color, size=18, strong=False, featured=False):
    """共用圓潤卡片，裝飾只改視覺，不影響資料。"""
    background=(f'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #30291D,stop:0.25 {COLORS["card"]},stop:0.8 #101112,stop:1 #282116)' if featured else
                f'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #1D1E20,stop:1 {COLORS["card"]})')
    if featured:background='transparent'
    return (f'font-size:{size}px;font-weight:{600 if strong else 400};color:{color};'
            f'background:{background};padding:14px;border:1px solid {COLORS["border"]};border-radius:16px;')
