import pytest
from poker.cards import DECK, validate_cards
from poker.evaluator import evaluate_hand
from poker.range import expand_range
from poker.equity import calculate_equity
from poker.pot_odds import required_equity, call_ev
from poker.bet_simulator import simulate_bets
from state.models import PokerTableState, PlayerState
from state.state_detector import StateDetector
from database.repository import StateRepository
from poker.outs import calculate_outs
from poker.engine import AnalysisEngine
from poker.range import save_range, load_range

def test_math_and_bets():
    assert required_equity(100, 50) == pytest.approx(1/3)
    assert call_ev(.5,100,50) == 25
    rows = simulate_bets(100, 40, .5)
    assert len(rows) == 7
    assert all(r.bet <= 40 for r in rows)
