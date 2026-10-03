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

def test_cards_and_range():
    assert len(set(DECK)) == 52
    with pytest.raises(ValueError): validate_cards(['As','As'])
    assert len(expand_range('AA')) == 6
    assert len(expand_range('AKs')) == 4
    assert len(expand_range('AKo')) == 12
    assert len(expand_range('AK')) == 16
    with pytest.raises(ValueError): expand_range('')

def test_evaluation():
    assert evaluate_hand(['As','Ks'], ['Qs','Js','Ts']).category == '同花順'
    assert '未成牌' in evaluate_hand(['As','Kd'], []).category

def test_evaluation_sizes_and_outs():
    assert evaluate_hand(['As','Ad'], ['Ac','Kh','Kd','2s','3s']).category == '葫蘆'
    assert evaluate_hand(['As','Ad'], ['Ac','Kh','Kd','2s']).category == '葫蘆'
    with pytest.raises(ValueError): evaluate_hand(['As','Ad'], ['Ac'])
    outs=calculate_outs(['As','Ad'], ['2c','7d','9h'])
    assert outs.count == 11
    assert '非乾淨' in outs.description
