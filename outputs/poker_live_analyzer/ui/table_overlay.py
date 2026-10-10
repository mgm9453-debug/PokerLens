from poker.amount_units import format_amount
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel,QPushButton


class TableOverlay(QWidget):
    open_main=Signal()
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        from .fonts import interface_font
        self.setFont(interface_font())
        self.setWindowTitle('牌局分析浮窗')
        self.display_options={}
        self.action_role=None
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

    def apply_display_options(self,options):
        self.display_options=dict(options)
        from .action_palette import action_color,readable_color
        color=readable_color(action_color(self.action_role,options))
        self.label.setStyleSheet(f'font-size:20px;font-weight:bold;color:{color};padding:8px;')

    def render(self, result, state):
        text=result.get('action_text','')
        self.action_role=result.get('action_role')
        if not self.action_role:
            for word,role in [('棄牌','fold_color'),('跟注','call_color'),('過牌','check_color'),('加注','raise_color')]:
                if word in text:self.action_role=role;break
        self.apply_display_options(self.display_options)
        if result.get('equity_only'):
            win=result.get('equity_details',{}).get('win_probability')
            self.label.setText('勝率已估算｜下注金額待確認')
            self.details.setText(f'勝率 {win:.1%}　平手 {result.get("tie_probability",0):.1%}\n對手 {result.get("opponents",0)} 人｜依假設手牌範圍估算\n金額不完整，暫停下注建議' if win is not None else '正在估算勝率')
            self.adjustSize()
            return
        call=state.get('call_amount',0)
        pot=state.get('pot',0)
        self.label.setText(result.get('action_text') or ('不用補錢｜行動待確認' if call==0 else '跟注估算待確認'))
        win=result.get('equity_details',{}).get('win_probability')
        ratio=format(call/pot,'.1%' if state.get('amount_unit')=='BB' else '.0%') if pot>0 else '待確認'
        probability=f'勝率 {win:.1%}' if win is not None else '勝率待確認'
        self.details.setText(f'{probability}　平手 {result.get("tie_probability",0):.1%}\n底池 {format_amount(pot,state.get('amount_unit','籌碼'))}　需跟注 {format_amount(call,state.get('amount_unit','籌碼'))}｜底池 {ratio}\n'+result.get('sizing_advice','加注建議：位置與加注歷史待確認'))
        self.adjustSize()

    def invalidate(self,message):
        self.action_role=None
        self.apply_display_options(self.display_options)
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
