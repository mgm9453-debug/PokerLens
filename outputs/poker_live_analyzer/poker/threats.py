"""列舉目前成牌可被哪些範圍底牌擊敗，不計算出現機率。"""
from dataclasses import dataclass,field,asdict
from time import perf_counter
from itertools import combinations
from treys import Card
from .evaluator import EVALUATOR,CATEGORIES,evaluate_hand
from .range import expand_range

@dataclass(frozen=True)
class ThreatsResult:
    beating_hand_types: list[str]
    label: str
    counts: dict[str,int] = field(default_factory=dict)
    combination_count: int = 0
    legal_combination_count: int = 0
    opponent_details: list[dict] = field(default_factory=list)
    milliseconds: float = 0.0
    visual_examples: list[dict] = field(default_factory=list)
    def to_dict(self): return asdict(self)

def calculate_threats(state,cancel=None):
    started=perf_counter()
    if len(state.hero_cards)!=2: raise ValueError('目前威脅列舉需要英雄兩張底牌')
    if len(state.board)==0:
        return ThreatsResult([], '翻牌前尚無當前成牌；目前威脅無法比較，請參考終局估計勝率',milliseconds=(perf_counter()-started)*1000)
    if len(state.board) not in (3,4,5): raise ValueError('目前威脅列舉需要三至五張公共牌')
    hero=evaluate_hand(state.hero_cards,state.board)
    board=[Card.new(c) for c in state.board]
    opponents=[p for p in state.players if p.seat!=state.hero_seat and p.active and not p.folded]
    legal_union=set()
    beaten_union=set()
    category_hands={}
    details=[]
    visual={}
    for opponent in opponents:
        # 未攤牌的底牌欄位不作資訊來源，僅採指定範圍。
        blocked=[*state.hero_cards,*state.board]
        if state.showdown:
            blocked.extend(c for p in opponents if p.seat!=opponent.seat for c in p.hole_cards)
        expression=[opponent.hole_cards] if state.showdown and opponent.hole_cards else state.ranges.get(str(opponent.seat),'標準')
        hands=expand_range(expression,blocked)
        legal_union.update(hands)
        own_counts={}
        examples={}
        own_beaten=0
        for index,hand in enumerate(hands):
            if index%64==0 and cancel and cancel(): raise InterruptedError('目前手牌威脅列舉已取消')
            score=EVALUATOR.evaluate(board,[Card.new(c) for c in hand])
            if score>=hero.score: continue
            rank=max(1,EVALUATOR.get_rank_class(score))
            label=CATEGORIES[rank]
            if rank==hero.category_rank: label+='（更高點數或踢腳）'
            category_hands.setdefault((rank,label),set()).add(hand)
            beaten_union.add(hand)
            if label not in visual:
                available=[*hand,*state.board]
                best=min(combinations(available,5),key=lambda cards:EVALUATOR.evaluate([],[Card.new(c) for c in cards]))
                visual[label]={'category':label,'hole_cards':list(hand),'best_five':list(best)}
            own_counts[label]=own_counts.get(label,0)+1
            own_beaten+=1
            if len(examples.setdefault(label,[]))<3: examples[label].append(list(hand))
        details.append({'seat':opponent.seat,'legal_combination_count':len(hands),'beating_combination_count':own_beaten,'counts':own_counts,'examples':examples})
    counts={label:len(hands) for (rank,label),hands in sorted(category_hands.items())}
    return ThreatsResult(list(counts),'僅比較目前公共牌，不補未來牌；合法底牌組合去重列舉，不是出現機率，也不是多對手聯合機率',counts,len(beaten_union),len(legal_union),details,(perf_counter()-started)*1000,[visual[label] for label in counts])
