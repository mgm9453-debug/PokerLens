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

def test_equity_split_and_seed():
    args = dict(hero=['2c','3d'], board=['As','Ks','Qs','Js','Ts'], opponent_ranges=['44','55'], iterations=10000, seed=7)
    a = calculate_equity(**args)
    assert a == calculate_equity(**args)
    assert a.hero_equity == pytest.approx(1/3)
    assert a.opponents_equity == pytest.approx(2/3)
    assert a.tie_probability == 1
    with pytest.raises(ValueError): calculate_equity(['As','Ah'], ['Ac','Ad','2d'], ['AA'], iterations=10000)

def test_ranges_and_cancellation(tmp_path):
    path=tmp_path/'range.json'
    save_range(path,'AA AKs')
    assert load_range(path)=='AA AKs'
    result=calculate_equity(['As','Kd'],[],['緊'],iterations=10000,cancel=lambda:True)
    assert result.cancelled and result.iterations_completed==0
    with pytest.raises(ValueError, match='彼此牌阻擋'): calculate_equity(['As','Kd'],[],[[('2c','3c')],[('2c','3c')]],iterations=10000)
    with pytest.raises(ValueError): expand_range('AAs')

def test_hidden_opponent_cards_and_engine_cancel():
    state=PokerTableState(hero_cards=['As','Ad'],board=['2c','3d','4h'],players=[PlayerState(1),PlayerState(2,hole_cards=['Ks','Kd'])],hero_seat=1,ranges={'2':'QQ'})
    engine=AnalysisEngine(iterations=10000)
    hidden=engine.analyze(state)
    state.players[1].hole_cards=[]
    assert hidden.equity==engine.analyze(state).equity
    with pytest.raises(InterruptedError): engine.analyze(state,cancel=lambda:True)
