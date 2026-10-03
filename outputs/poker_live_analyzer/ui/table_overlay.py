from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel,QPushButton


class TableOverlay(QWidget):
    open_main=Signal()
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        from .fonts import interface_font
        self.setFont(interface_font())
        self.setWindowTitle('牌局分析浮窗')
        self.drag_origin=None
        self.setFixedWidth(380)
        from .theme import STYLE
        self.setStyleSheet(STYLE)
        layout=QVBoxLayout(self)
        layout.setContentsMargins(14,10,14,12)
        header=QHBoxLayout()
        header.addWidget(QLabel('牌局分析｜拖動此處移動'))
        main=QPushButton('開啟視窗')
        main.clicked.connect(self.open_main.emit)
        header.addWidget(main)
        layout.addLayout(header)
        self.label = QLabel('等待確認')
        self.label.setWordWrap(True)
        self.label.setStyleSheet('font-size:20px;font-weight:bold;color:#47e3bd;padding:8px;')
        layout.addWidget(self.label)
        self.details=QLabel()
        self.details.setWordWrap(True)
        self.details.setStyleSheet('font-size:16px;color:#cbdbe9;padding:8px;')
        layout.addWidget(self.details)

    def render(self, result, state):
        call=state.get('call_amount',0)
        pot=state.get('pot',0)
        self.label.setText(result.get('action_text') or ('不用補錢｜行動待確認' if call==0 else '跟注估算待確認'))
        win=result.get('equity_details',{}).get('win_probability')
        ratio=f'{call/pot:.0%}' if pot>0 else '待確認'
        probability=f'勝率 {win:.1%}' if win is not None else '勝率待確認'
        self.details.setText(f'{probability}　平手 {result.get("tie_probability",0):.1%}\n底池 {pot:,.0f}　需跟注 {call:,.0f}｜底池 {ratio}\n'+result.get('sizing_advice','加注建議：位置與加注歷史待確認'))
        self.adjustSize()

    def invalidate(self,message):
        self.label.setText(message.split('\n')[0])
        self.details.clear()
        self.adjustSize()

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.drag_origin=event.globalPosition().toPoint()-self.pos()
            event.accept()

    def mouseMoveEvent(self,event):
        if self.drag_origin is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint()-self.drag_origin)
            event.accept()

    def mouseReleaseEvent(self,event):
        self.drag_origin=None
        event.accept()

    def set_pinned(self, pinned):
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, pinned)
        if visible:
            self.show()
