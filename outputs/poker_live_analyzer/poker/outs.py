from dataclasses import dataclass
from .cards import DECK, validate_cards
from .evaluator import evaluate_hand

@dataclass(frozen=True)
class OutsResult:
    count: int
    cards: list[str]
    description: str = '下一張提升牌型類別的補牌，非乾淨補牌，不保證勝出'

def calculate_outs(hero, board):
    known = validate_cards([*hero,*board])
    if len(board) not in (3,4): return OutsResult(0, [], '僅翻牌及轉牌提供下一張牌型提升補牌；非乾淨補牌')
    rank = evaluate_hand(hero,board).category_rank
    cards = [c for c in DECK if c not in known and evaluate_hand(hero,[*board,c]).category_rank < rank]
    return OutsResult(len(cards),cards)
