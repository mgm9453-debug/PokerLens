from dataclasses import dataclass, field, asdict
import math
from poker.cards import validate_cards
from poker.pot_odds import nonnegative

@dataclass
class PlayerState:
    seat: int
    name: str = ''
    position: str = ''
    stack: float = 0.0
    stack_known: bool = True
    bet: float = 0.0
    current_bet: float | None = None
    total_invested: float | None = None
    action: str = ''
    active: bool = True
    folded: bool = False
    all_in: bool = False
    hole_cards: list[str] = field(default_factory=list)
    confidence: dict[str,float] = field(default_factory=dict)
    def __post_init__(self):
        if self.current_bet is not None: self.bet=self.current_bet
        self.current_bet=self.bet
        if self.total_invested is None: self.total_invested=self.current_bet
        if any(not isinstance(v,bool) for v in (self.active,self.folded,self.all_in,self.stack_known)): raise ValueError('玩家狀態控制須為布林值')
        if isinstance(self.seat,bool) or not isinstance(self.seat,int) or self.seat<0: raise ValueError('座位須為非負整數')
        nonnegative(self.stack,'籌碼'); nonnegative(self.bet,'下注')
        nonnegative(self.total_invested,'累計投入')
        if self.total_invested<self.current_bet: raise ValueError('累計投入不可小於目前下注')
        validate_cards(self.hole_cards)
        if len(self.hole_cards) not in (0,2): raise ValueError('玩家底牌須為零或兩張')
        validate_confidence(self.confidence)
    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls,data): return cls(**data)

def validate_confidence(confidence):
    for value in confidence.values():
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('信心須為零至一之間有限數值')

@dataclass
class PokerTableState:
    hero_cards: list[str] = field(default_factory=list)
    board: list[str] = field(default_factory=list)
    community_cards: list[str] | None = None
    players: list[PlayerState] = field(default_factory=list)
    hero_seat: int | None = None
    pot: float = 0.0
    call_amount: float = 0.0
    effective_stack: float = 0.0
    hero_stack: float = 0.0
    small_blind: float = 0.0
    big_blind: float = 0.0
    dealer_seat: int | None = None
    dealer_position: int | None = None
    street: str = ''
    showdown: bool = False
    hand_complete: bool = False
    hand_id: str = ''
    table_id: str = ''
    timestamp: float = 0.0
    source: str = '手動'
    confidence: dict[str,float] = field(default_factory=dict)
    ranges: dict[str,str] = field(default_factory=dict)
    fold_probability: float = 0.0
    def __post_init__(self):
        if self.community_cards is not None: self.board=list(self.community_cards)
        self.community_cards=list(self.board)
        if self.dealer_position is not None: self.dealer_seat=self.dealer_position
        self.dealer_position=self.dealer_seat
        if any(not isinstance(v,bool) for v in (self.showdown,self.hand_complete)): raise ValueError('攤牌及完成控制須為布林值')
        self.players=[PlayerState.from_dict(p) if isinstance(p,dict) else p for p in self.players]
        if len(self.hero_cards) not in (0,2) or len(self.board) not in (0,3,4,5): raise ValueError('底牌或公共牌張數錯誤')
        seats=[p.seat for p in self.players]
        if len(set(seats))!=len(seats): raise ValueError('玩家座位重複')
        for seat in (self.hero_seat,self.dealer_seat):
            if seat is not None and (isinstance(seat,bool) or not isinstance(seat,int) or seat<0): raise ValueError('座位須為非負整數')
            if seat is not None and seat not in seats: raise ValueError('指定座位不存在於玩家清單')
        if any(str(k) not in {str(s) for s in seats} for k in self.ranges): raise ValueError('對手範圍座位不存在')
        known=[*self.hero_cards,*self.board]
        for p in self.players:
            if p.seat==self.hero_seat and p.hole_cards:
                if p.hole_cards!=self.hero_cards: raise ValueError('英雄底牌欄位不一致')
            else: known.extend(p.hole_cards)
        validate_cards(known)
        for name,label in (('pot','底池'),('call_amount','跟注額'),('effective_stack','有效籌碼'),('hero_stack','英雄籌碼'),('small_blind','小盲注'),('big_blind','大盲注'),('timestamp','時間戳')): nonnegative(getattr(self,name),label)
        if self.pot+1e-9<sum(p.current_bet for p in self.players): raise ValueError('底池不可小於所有玩家目前下注總和')
        if self.hero_stack and (self.effective_stack>self.hero_stack or self.call_amount>self.hero_stack): raise ValueError('有效籌碼與跟注額不可超過英雄籌碼')
        from poker.pot_odds import probability
        probability(self.fold_probability)
        validate_confidence(self.confidence)
        inferred='等待' if not self.hero_cards and not self.board else {0:'翻牌前',3:'翻牌',4:'轉牌',5:'河牌'}[len(self.board)]
        expected='完成' if self.hand_complete else '攤牌' if self.showdown else inferred
        self.street={'waiting':'等待','WAITING':'等待','preflop':'翻牌前','flop':'翻牌','turn':'轉牌','river':'河牌','showdown':'攤牌','complete':'完成'}.get(self.street,self.street)
        if self.street and self.street!=expected: raise ValueError('街次與公共牌或完成控制不一致')
        self.street=expected
    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls,data): return cls(**data)
