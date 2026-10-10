from dataclasses import dataclass, asdict, field
import time
from .evaluator import evaluate_hand,CATEGORIES
from .equity import calculate_equity
from .pot_odds import required_equity, call_ev, spr
from .outs import calculate_outs
from .bet_simulator import simulate_bets
from .threats import calculate_threats
from .starting_hands import starting_hand_guide
from .published_equity import optional_reference
from state.models import PokerTableState

@dataclass
class AnalysisResult:
    hand_strength: str
    equity: float
    opponent_equity: float
    tie_probability: float
    required_equity: float
    pot_odds: float
    ev: float
    spr: float | None
    outs: int
    bet_scenarios: list[dict]
    simulation_count: int
    timestamp: float
    equity_details: dict
    outs_details: dict
    simulation_seed: int = 42
    requested_simulations: int = 100000
    assumption: str = '下注情境假設一位對手跟注；補牌非乾淨補牌；蒙地卡羅結果為估計值'
    beating_hand_types: list[str] = field(default_factory=list)
    threats_details: dict = field(default_factory=dict)
    starting_hand: dict = field(default_factory=dict)
    def to_dict(self): return asdict(self)

class AnalysisEngine:
    def __init__(self,iterations=100000,seed=42,*,time_budget=None,cooperative=False):
        self.iterations=iterations; self.seed=seed
        self.time_budget=time_budget; self.cooperative=cooperative
    @staticmethod
    def equity_key(state,seed=42):
        return (seed, tuple(state.hero_cards), tuple(state.board), state.showdown,
            tuple((p.seat, tuple(p.hole_cards) if state.showdown else (), state.ranges.get(str(p.seat),'標準'))
                for p in state.players if p.seat != state.hero_seat and p.active and not p.folded))
    def analyze(self,state,cancel=None,cached_equity=None):
        if cancel and cancel(): raise InterruptedError('分析已取消')
        state=PokerTableState.from_dict(state.to_dict())
        if len(state.hero_cards)!=2: raise ValueError('需提供英雄兩張底牌')
        if state.hero_seat is None or state.hero_seat not in {p.seat for p in state.players}:
            raise ValueError('請指定自身玩家座位，避免將自身誤算為對手')
        opponents=[p for p in state.players if p.seat!=state.hero_seat and p.active and not p.folded]
        ranges=[]
        for p in opponents:
            if p.hole_cards and state.showdown: ranges.append([p.hole_cards])
            else: ranges.append(state.ranges.get(str(p.seat),'標準'))
        if not ranges: raise ValueError('需至少一位仍在牌局中的對手')
        guide=starting_hand_guide(state.hero_cards,state.board)
        if guide:
            guide['published_reference']=optional_reference(state.hero_cards,state.board,ranges)
        if cached_equity is not None and cached_equity[0] != self.equity_key(state,self.seed):
            raise ValueError('權益快取與目前牌面或對手範圍不一致')
        equity=cached_equity[1] if cached_equity is not None else calculate_equity(state.hero_cards,state.board,ranges,self.iterations,self.seed,cancel,time_budget=self.time_budget,cooperative=self.cooperative)
        if equity.cancelled: raise InterruptedError('分析已取消，不產生勝率或期望值結果')
        outs=calculate_outs(state.hero_cards,state.board)
        needed=required_equity(state.pot,state.call_amount)
        threats=calculate_threats(state,cancel)
        threat_details=threats.to_dict()
        threat_details['terminal_beating_counts']=equity.terminal_beating_counts
        threat_details['terminal_simulation_count']=equity.iterations_completed
        threat_types=threats.beating_hand_types
        if not state.board:
            threat_types=[CATEGORIES[rank] for rank in range(1,10) if CATEGORIES[rank] in equity.terminal_beating_counts]
            threat_details['beating_hand_types']=threat_types
            threat_details['label']='翻牌前尚無當前成牌；終局觀察：模擬觀察到的終局擊敗牌型，不是完整可能清單或出現機率；兩千次快速估算與後續增加次數可能觀察到不同類型'
        if cancel and cancel(): raise InterruptedError('分析已取消')
        return AnalysisResult(evaluate_hand(state.hero_cards,state.board).category,equity.hero_equity,equity.opponents_equity,equity.tie_probability,needed,needed,call_ev(equity.hero_equity,state.pot,state.call_amount),spr(state.effective_stack,state.pot),outs.count,[asdict(r) for r in simulate_bets(state.pot,state.effective_stack,equity.hero_equity,state.fold_probability)],equity.iterations_completed,time.time(),equity.to_dict(),asdict(outs),simulation_seed=self.seed,requested_simulations=equity.iterations_completed if cached_equity is not None else self.iterations,beating_hand_types=threat_types,threats_details=threat_details,starting_hand=guide)
