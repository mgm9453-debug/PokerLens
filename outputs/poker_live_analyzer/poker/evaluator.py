from dataclasses import dataclass
from treys import Card, Evaluator
from .cards import validate_cards

EVALUATOR = Evaluator()
CATEGORIES = {0:'同花順', 1:'同花順', 2:'四條', 3:'葫蘆', 4:'同花', 5:'順子', 6:'三條', 7:'兩對', 8:'一對', 9:'高牌'}

@dataclass(frozen=True)
class HandEvaluation:
    score: int | None
    category: str
    category_rank: int | None

def evaluate_hand(hole, board=()):
    cards = validate_cards([*hole, *board])
    if len(cards) == 2:
        return HandEvaluation(None, '翻牌前未成牌，勝率須依對手範圍估算', None)
    if not 5 <= len(cards) <= 7:
        raise ValueError('牌型評估需要五至七張牌')
    score = EVALUATOR.evaluate([], [Card.new(c) for c in cards])
    rank = max(1, EVALUATOR.get_rank_class(score))
    return HandEvaluation(score, CATEGORIES[rank], rank)
