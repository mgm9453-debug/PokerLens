import random
from dataclasses import dataclass, asdict, field
from treys import Card
from .cards import DECK, validate_cards
from .evaluator import EVALUATOR,CATEGORIES
from .range import expand_range

ITERATIONS = (2000,10000,50000,100000,500000,1000000)

@dataclass(frozen=True)
class EquityResult:
    hero_equity: float
    opponents_equity: float
    tie_probability: float
    win_probability: float
    iterations_completed: int
    cancelled: bool = False
    terminal_beating_counts: dict[str,int] = field(default_factory=dict)
    def to_dict(self): return asdict(self)

def calculate_equity(hero, board, opponent_ranges, iterations=100000, seed=42, cancel=None):
    known = validate_cards([*hero,*board])
    if len(hero)!=2 or len(board) not in (0,3,4,5): raise ValueError('底牌或公共牌張數錯誤')
    if iterations not in ITERATIONS: raise ValueError('模擬次數須為兩千、一萬、五萬、十萬、五十萬或一百萬')
    if not opponent_ranges: raise ValueError('至少需要一位對手範圍')
    ranges = [expand_range(r,known) for r in opponent_ranges]
    if len(known)+2*len(ranges)+5-len(board)>52: raise ValueError('對手人數超過牌組容量')
    # 先證明範圍存在互不重疊的組合，避免不可能輸入陷入重試。
    def feasible(index, used):
        if index == len(ranges): return True
        return any(feasible(index+1, used|set(h)) for h in ranges[index] if not used.intersection(h))
    if not feasible(0,set(known)): raise ValueError('對手範圍彼此牌阻擋，無合法組合')
    rng = random.Random(seed)
    encoded = {c:Card.new(c) for c in DECK}
    hero_int = [encoded[c] for c in hero]
    hero_share=ties=wins=completed=0
    cancelled=False
    terminal_counts={}
    for i in range(iterations):
        if i % 64 == 0 and cancel and cancel():
            cancelled=True
            break
        # 聯合拒絕抽樣，使每位對手各自範圍的合法聯合組合均勻。
        for attempt in range(100000):
            hands=[rng.choice(r) for r in ranges]
            drawn=[c for h in hands for c in h]
            if len(set(drawn)) == len(drawn): break
            if attempt % 64 == 0 and cancel and cancel():
                cancelled=True
                break
        else: raise ValueError('合法範圍組合過於稀少，請縮小對手範圍')
        if cancelled: break
        used=set(known)|set(drawn)
        full_board=[*board,*rng.sample([c for c in DECK if c not in used],5-len(board))]
        board_int=[encoded[c] for c in full_board]
        scores=[EVALUATOR.evaluate(board_int,hero_int), *[EVALUATOR.evaluate(board_int,[encoded[c] for c in h]) for h in hands]]
        best=min(scores)
        winners=scores.count(best)
        if scores[0]==best:
            hero_share+=1/winners
            ties+=winners>1
            wins+=winners==1
        else:
            # 只記錄英雄真正輸掉的終局最佳對手牌型，每次模擬只計一次。
            category=CATEGORIES[max(1,EVALUATOR.get_rank_class(best))]
            terminal_counts[category]=terminal_counts.get(category,0)+1
        completed+=1
    if not completed: return EquityResult(0,0,0,0,0,True)
    share=hero_share/completed
    return EquityResult(share,1-share,ties/completed,wins/completed,completed,cancelled,terminal_counts)
