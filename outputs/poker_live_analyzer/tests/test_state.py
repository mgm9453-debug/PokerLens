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

def test_detector_and_replay(tmp_path):
    state = PokerTableState(hero_cards=['As','Kd'], players=[PlayerState(seat=1, stack=100)], hero_seat=1, pot=10)
    detector = StateDetector()
    event = detector.update(state)
    assert event.version == 1
    assert detector.update(PokerTableState.from_dict({**state.to_dict(), 'timestamp': 99})) is None
    assert detector.update(PokerTableState.from_dict({**state.to_dict(), 'pot':20}), {'pot':.84}) is None
    assert detector.state.pot == 10
    with pytest.raises(ValueError): PokerTableState(pot=float('nan'))
    repo = StateRepository(tmp_path/'history.db')
    repo.save_event(event)
    assert repo.list_events()[0]['current_state']['hero_cards'] == ['As','Kd']
    repo.close()

def test_validation_streets_and_nested_confidence():
    state=PokerTableState(board=['2c','3c','4c'])
    assert state.street=='翻牌'
    assert PokerTableState(board=['2c','3c','4c','5c','6c'],showdown=True).street=='攤牌'
    assert PokerTableState(hand_complete=True).street=='完成'
    with pytest.raises(ValueError): PokerTableState(board=['2c'])
    with pytest.raises(ValueError): PokerTableState(players=[PlayerState(1),PlayerState(1)])
    with pytest.raises(ValueError): PlayerState(1,stack=-1)
    detector=StateDetector()
    assert detector.update(PokerTableState(players=[PlayerState(1,confidence={'stack':.84})])) is None
    assert detector.update(PokerTableState(confidence={'pot':.85})) is not None
    assert detector.update({'pot':float('inf')}) is None
    with pytest.raises(ValueError): PokerTableState(showdown='是')
    with pytest.raises(ValueError): PlayerState(1, folded='否')

def test_waiting_and_transition_rejection():
    assert PokerTableState().street=='等待'
    detector=StateDetector()
    assert detector.update(PokerTableState(hero_cards=['As','Kd'],hand_id='甲',source='假資料'))
    assert detector.update(PokerTableState(hero_cards=['As','Kd'],board=['2c','3d','4h','5s'],hand_id='甲',source='假資料')) is None
    assert detector.update(PokerTableState(hero_cards=['As','Kd'],board=['2c','3d','4h'],hand_id='甲',source='假資料'))
    assert detector.update(PokerTableState(hero_cards=['As','Kd'],hand_id='甲',source='假資料')) is None
    assert detector.update(PokerTableState(hero_cards=['As','Kd'],hand_id='乙',source='假資料'))
    assert detector.update(PokerTableState(hero_cards=['As','Kd'],hand_id='乙',source='手動',board=['2c','3d','4h','5s']))
    first=detector.state.timestamp
    assert first>0
    event=detector.update(PokerTableState(hero_cards=['As','Kd'],hand_id='乙',source='手動',board=['2c','3d','4h','5s','6c']))
    assert event.timestamp>first

def test_inconsistent_amounts_and_seats():
    with pytest.raises(ValueError): PokerTableState(pot=5,players=[PlayerState(1,current_bet=6)])
    with pytest.raises(ValueError): PlayerState(1,current_bet=6,total_invested=5)
    with pytest.raises(ValueError): PokerTableState(hero_stack=10,effective_stack=11)
    with pytest.raises(ValueError): PokerTableState(hero_stack=10,call_amount=11)
    with pytest.raises(ValueError): PokerTableState(hero_seat=3,players=[PlayerState(1)])

def test_complete_sequence_and_explicit_reset():
    detector=StateDetector()
    common={'hero_cards':['As','Kd'],'hand_id':'一','source':'假資料'}
    for board in ([],['2c','3d','4h'],['2c','3d','4h','5s'],['2c','3d','4h','5s','6c']):
        assert detector.update(PokerTableState(**common,board=board))
    assert detector.update(PokerTableState(**common,board=board,showdown=True))
    assert detector.update(PokerTableState(**common,board=board,showdown=True,hand_complete=True))
    assert detector.update(PokerTableState(hand_id='一',source='假資料'))
    assert detector.state.street=='等待'
    assert detector.update(PokerTableState(**common,board=board),reset=True)
    with pytest.raises(ValueError): PokerTableState(players=[PlayerState(1)],ranges={'2':'AA'})

def test_explicit_zero_investment_and_compatibility():
    with pytest.raises(ValueError): PlayerState(1,current_bet=100,total_invested=0)
    assert PlayerState(1,current_bet=100).total_invested==100
    from poker.hand_evaluator import HandEvaluation, evaluate_hand as compatible_evaluate
    from poker.ev import call_ev as compatible_ev
    assert isinstance(compatible_evaluate(['As','Kd']),HandEvaluation)
    assert compatible_ev(.5,100,50)==25
