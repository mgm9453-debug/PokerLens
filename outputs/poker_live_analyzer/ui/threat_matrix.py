"""白底起手牌矩陣，標示目前公共牌下能擊敗自己的合法組合。"""
from functools import lru_cache
from itertools import combinations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView
from PySide6.QtGui import QColor
from treys import Card
from poker.cards import DECK
from poker.evaluator import EVALUATOR,evaluate_hand

RANKS='AKQJT98765432'

def hand_key(hand):
    first,second=sorted(hand,key=lambda card:RANKS.index(card[0]))
    return first[0]+second[0]+('' if first[0]==second[0] else 's' if first[1]==second[1] else 'o')

def card_names(cards):
    suits={'s':'黑桃','c':'梅花','h':'紅心','d':'方塊'}
    ranks={'T':'十','J':'傑克','Q':'皇后','K':'國王','A':'王牌'}
    return '、'.join(suits[c[1]]+ranks.get(c[0],c[0]) for c in cards)

@lru_cache(maxsize=32)
def winning_cells(hero,board):
    if len(hero)!=2 or len(board) not in (3,4,5): return {}
    score=evaluate_hand(hero,board).score
    blocked=set(hero+board)
    available=[card for card in DECK if card not in blocked]
    encoded=[Card.new(card) for card in board]
    cells={}
    for hand in combinations(available,2):
        if EVALUATOR.evaluate(encoded,[Card.new(card) for card in hand])<score:
            cells.setdefault(hand_key(hand),[]).append(hand)
    return cells

class ThreatMatrix(QWidget):
    def __init__(self):
        super().__init__()
        layout=QVBoxLayout(self)
        layout.setContentsMargins(0,4,0,4)
        self.caption=QLabel('s＝同花｜o＝不同花｜兩個相同點數＝口袋對子')
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption)
        self.table=QTableWidget(13,13)
        from .reference_style import RoundedCellDelegate
        self.table.setItemDelegate(RoundedCellDelegate(self.table))
        self.table.setShowGrid(False)
        self.table.setHorizontalHeaderLabels(list(RANKS))
        self.table.setVerticalHeaderLabels(list(RANKS))
        # 固定字體與格子尺寸，視窗縮小時捲動而不壓縮牌型。
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setMinimumSectionSize(32)
        self.table.horizontalHeader().setDefaultSectionSize(51)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setMinimumSectionSize(22)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.horizontalHeader().setFixedHeight(30)
        self.table.verticalHeader().setFixedWidth(28)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setMinimumHeight(320)
        self.table.setStyleSheet('QTableWidget {background:#08090A;color:#142433;gridline-color:#348A69;font-size:14px;font-weight:500;border:1px solid #9B7133;} QHeaderView::section {background:#EFC67A;color:#17120A;font-weight:600;padding:1px;border:1px solid #08090A;border-radius:4px;} QTableWidget::item {padding:0px;}')
        layout.addWidget(self.table,1)
        self.note=QLabel('上三角：同花；下三角：不同花；對角線：對子。比較所有合法底牌，不代表對手實際持牌或機率。')
        self.note.setWordWrap(True)
        self.note.hide()
        self.background='#00cc66'
        self.winner='#ef4444'
        self.last_key=None
        self.render([],[])

    def render(self,hero,board):
        self.setEnabled(True)
        self.table.setToolTip('依目前已確認牌面比較；標示色代表至少一種合法花色組合能贏你。')
        key=(tuple(hero),tuple(board))
        if key==self.last_key:
            if len(hero)==2 and len(board) in (3,4,5):self.caption.setText('s＝同花｜o＝不同花｜兩個相同點數＝口袋對子')
            return
        self.last_key=key
        cells=winning_cells(*key)
        ready=len(hero)==2 and len(board) in (3,4,5)
        self.caption.setText('s＝同花｜o＝不同花｜兩個相同點數＝口袋對子' if ready else 's＝同花｜o＝不同花｜兩個相同點數＝口袋對子')
        for row,a in enumerate(RANKS):
            for column,b in enumerate(RANKS):
                name=a+b if row==column else a+b+'s' if row<column else b+a+'o'
                item=QTableWidgetItem(name)
                item.setTextAlignment(Qt.AlignCenter)
                background=self.winner if name in cells else self.background
                from .theme import COLORS
                background={'#00cc66':COLORS['matrix'],'#ef4444':COLORS['winner']}.get(background,background)
                item.setForeground(QColor(self.text_color(background)))
                item.setBackground(QColor(background))
                hands=cells.get(name,[])
                item.setToolTip(f'{name}：目前有 {len(hands)} 種合法組合能贏你\n'+ '\n'.join(card_names(hand) for hand in hands) if hands else f'{name}：目前未找到能贏你的合法組合' if ready else f'{name}：等待牌面，尚未比較')
                self.table.setItem(row,column,item)

    @staticmethod
    def text_color(background):
        color=QColor(background)
        channels=[value/12.92 if value<=.04045 else ((value+.055)/1.055)**2.4
            for value in (color.redF(),color.greenF(),color.blueF())]
        luminance=sum(value*weight for value,weight in zip(channels,(.2126,.7152,.0722)))
        return '#000000' if luminance>.179 else '#ffffff'

    def invalidate(self):
        """保留全部牌型與位置，清除上次比較標色及提示。"""
        self.render([],[])
        self.setEnabled(False)
        self.table.setToolTip('牌面尚未確認；矩陣尚未比較。')

    def apply_colors(self,background,winner):
        if (background,winner)==(self.background,self.winner):return
        enabled=self.isEnabled()
        self.background,self.winner=background,winner
        key=self.last_key or ((),())
        self.last_key=None
        self.render(*key)
        self.setEnabled(enabled)
