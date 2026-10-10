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
    def __init__(self,preflop_path=None):
        super().__init__()
        layout=QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(2)
        self.caption=QLabel('')
        self.caption.setWordWrap(True)
        self.caption.setStyleSheet('font-family:"Inter","GenSenRounded2 TW","Noto Sans TC";font-size:14px;color:white;')
        layout.addWidget(self.caption)
        self.legend=QLabel()
        self.legend.setWordWrap(True)
        self.legend.setStyleSheet('font-family:"Inter","GenSenRounded2 TW","Noto Sans TC";font-size:19px;font-weight:500;color:white;padding:3px 0;')
        layout.addWidget(self.legend)
        self.table=QTableWidget(13,13)
        from .reference_style import RoundedCellDelegate
        self.table.setItemDelegate(RoundedCellDelegate(self.table))
        self.table.setShowGrid(False)
        self.table.setHorizontalHeaderLabels(list(RANKS))
        self.table.setVerticalHeaderLabels(list(RANKS))
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.table.verticalHeader().setDefaultAlignment(Qt.AlignCenter)
        # 保留可讀的最小格子尺寸，全部牌型一起縮放，不用捲動閱讀。
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setMinimumSectionSize(32)
        self.table.horizontalHeader().setDefaultSectionSize(51)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setMinimumSectionSize(22)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.horizontalHeader().setFixedHeight(30)
        self.table.verticalHeader().setFixedWidth(28)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setMinimumSize(13*32+28+4,13*22+30+4)
        self.table.setStyleSheet('QTableWidget {background:#08090A;color:#142433;gridline-color:#348A69;font-size:14px;font-weight:500;border:1px solid #9B7133;} QHeaderView::section {background:#EFC67A;color:#17120A;font-weight:600;padding:1px;border:1px solid #08090A;border-radius:4px;} QTableWidget::item {padding:0px;}')
        layout.addWidget(self.table,1)
        self.note=QLabel('')
        self.note.setWordWrap(True)
        self.note.hide()
        self.background='#00cc66'
        self.winner='#ef4444'
        self.last_key=None
        self.preflop_context=None
        self.preflop_colors={'preflop_background':'#34373b','preflop_raise':'#9d2638',
            'preflop_call':'#087553','preflop_fold':'#182333','preflop_check':'#655124'}
        from poker.preflop import RangeBook
        from app_paths import user_data_dir
        self.range_error=''
        try:
            self.range_book=RangeBook.load(preflop_path if preflop_path is not None else user_data_dir()/'ranges'/'mtt-preflop.json')
        except (ValueError,OSError):
            self.range_book=RangeBook()
            self.range_error='範圍檔案格式無效，未套用'
        self.render_preflop({})

    def render(self,hero,board):
        self.preflop_context=None
        self.caption.clear()
        self.caption.hide()
        self.update_legend(False)
        self.table.horizontalHeader().setStyleSheet('')
        self.table.verticalHeader().setStyleSheet('')
        self.setEnabled(True)
        self.table.setToolTip('依目前已確認牌面比較；標示色代表至少一種合法花色組合能贏你。')
        key=(tuple(hero),tuple(board))
        if key==self.last_key:
            return
        self.last_key=key
        cells=winning_cells(*key)
        ready=len(hero)==2 and len(board) in (3,4,5)
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

    def render_preflop(self,context,book=None):
        """翻前範圍獨立於勝率模擬；未知格保持灰色，不補成棄牌。"""
        from poker.preflop import RangeBook
        self.setEnabled(True)
        self.preflop_context=dict(context or {})
        if book is not None:self.range_book=book
        context=self.preflop_context
        key=('翻前',repr(context),repr(self.preflop_colors),id(self.range_book))
        if key==self.last_key:return
        self.last_key=key
        chart=self.range_book.match(context)
        hero=context.get('hero_cards',[])
        own=hand_key(hero) if len(hero)==2 else None
        position=context.get('position') or '位置確認中'
        stack=context.get('stack_bb')
        depth=f'｜{stack:g} BB' if stack is not None else ''
        scenarios={'open':'未開池','vs_open':'面對加注','vs_3bet':'面對再加注',
            'vs_4bet':'面對四次下注','vs_limp':'前面有人跟入','bb_option':'大盲可過牌'}
        spot=scenarios.get(context.get('scenario'),'情境確認中')
        status='已匹配範圍' if chart else '無對應範圍'
        self.caption.setText(f'{position}｜{own or "底牌確認中"}{depth}｜{spot}｜{status}')
        self.caption.show()
        self.update_legend(True)
        if not own and not context.get('position'):
            self.caption.clear()
            self.caption.hide()
        self.table.horizontalHeader().setStyleSheet('')
        self.table.verticalHeader().setStyleSheet('')
        self.table.setToolTip(f'來源：{chart["source"]}；求解：{chart["solver"]}' if chart else self.range_error or context.get('reason','尚無條件相符且來源已核實的錦標賽範圍'))
        labels={'raise':'加注','call':'跟注','fold':'棄牌','check':'過牌'}
        for row,a in enumerate(RANKS):
            for column,b in enumerate(RANKS):
                name=a+b if row==column else a+b+'s' if row<column else b+a+'o'
                frequencies=chart['hands'].get(name) if chart else None
                item=QTableWidgetItem(name)
                item.setTextAlignment(Qt.AlignCenter)
                item.setForeground(QColor('#ffffff'))
                segments=[]
                details=[]
                if frequencies:
                    for action,fraction in frequencies.items():
                        if fraction>0:
                            segments.append((self.preflop_colors['preflop_'+action],fraction))
                            details.append(f'{labels[action]} {fraction:.0%}')
                    remainder=max(0,1-sum(frequencies.values()))
                    if remainder>1e-9:
                        segments.append((self.preflop_colors['preflop_background'],remainder))
                        details.append(f'未提供策略 {remainder:.0%}')
                item.setBackground(QColor(segments[0][0] if segments else self.preflop_colors['preflop_background']))
                item.setData(Qt.UserRole+1,segments)
                item.setData(Qt.UserRole+2,name==own)
                item.setToolTip(f'{name}：'+('／'.join(details) if details else '無對應策略資料，不代表棄牌'))
                self.table.setItem(row,column,item)

    def update_legend(self,preflop):
        """圖例放在圖表上方；文字與配色一致，不混用行動與牌力顏色。"""
        if preflop:
            entries=[(self.preflop_colors['preflop_'+key],label) for key,label in
                (('raise','加注'),('call','跟注'),('check','過牌'),('fold','棄牌'),('background','無資料'))]
        else:
            from .theme import COLORS
            entries=[(COLORS['matrix'] if self.background=='#00cc66' else self.background,'一般牌型'),
                (COLORS['winner'] if self.winner=='#ef4444' else self.winner,'目前能贏你的牌')]
        # 以分開的文字與色點標示，保留設定配色且避免深色文字難以閱讀。
        cells=[]
        for color,label in entries:
            source=QColor(color)
            tint=QColor(*(round(channel*.45+255*.55) for channel in (source.red(),source.green(),source.blue()))).name()
            cells.append(f'<td><span style="color:{tint};">●　{label}</span></td>')
        self.legend.setText('<table width="100%" cellspacing="0" cellpadding="0"><tr>'+''.join(cells)+
            '</tr></table><span style="font-size:15px;font-weight:400;color:#e6e3dd;">s＝同花　｜　o＝不同花</span>')

    def apply_preflop_colors(self,options):
        changed={key:options[key] for key in self.preflop_colors if key in options and options[key]!=self.preflop_colors[key]}
        if not changed:return
        self.preflop_colors.update(changed)
        if self.preflop_context is not None:
            enabled=self.isEnabled()
            context=self.preflop_context
            self.last_key=None
            self.render_preflop(context)
            self.setEnabled(enabled)

    @staticmethod
    def text_color(background):
        color=QColor(background)
        channels=[value/12.92 if value<=.04045 else ((value+.055)/1.055)**2.4
            for value in (color.redF(),color.greenF(),color.blueF())]
        luminance=sum(value*weight for value,weight in zip(channels,(.2126,.7152,.0722)))
        return '#000000' if luminance>.179 else '#ffffff'

    def invalidate(self):
        """保留全部牌型與位置，清除上次比較標色及提示。"""
        self.render_preflop({})
        self.setEnabled(False)
        self.table.setToolTip('牌面尚未確認；矩陣尚未比較。')

    def apply_colors(self,background,winner):
        if (background,winner)==(self.background,self.winner):return
        enabled=self.isEnabled()
        self.background,self.winner=background,winner
        if self.preflop_context is not None:
            self.setEnabled(enabled)
            return
        key=self.last_key or ((),())
        self.last_key=None
        self.render(*key)
        self.setEnabled(enabled)
