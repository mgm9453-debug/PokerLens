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

def test_engine_and_analysis_storage(tmp_path):
    state=PokerTableState(hero_cards=['2c','3d'],board=['As','Ks','Qs','Js','Ts'],players=[PlayerState(1),PlayerState(2)],hero_seat=1,pot=100,call_amount=50,effective_stack=100,ranges={'2':'44'})
    result=AnalysisEngine(iterations=10000).analyze(state)
    assert result.equity==.5
    assert result.ev==25
    repo=StateRepository(tmp_path/'analysis.db')
    repo.save_analysis(1,result)
    assert repo.get_analysis(1)==result.to_dict()
    repo.close()

def test_public_state_and_analysis_interface():
    state=PokerTableState.from_dict({'hero_cards':['2c','3d'],'community_cards':['As','Ks','Qs','Js','Ts'],'hero_stack':100,'pot':10,'dealer_position':2,'players':[{'seat':1,'current_bet':10,'total_invested':20},{'seat':2}],'hero_seat':1,'street':'river'})
    assert state.board==state.community_cards
    assert state.hero_stack==100
    assert state.players[0].current_bet==10
    result=AnalysisEngine(iterations=10000).analyze(state).to_dict()
    for key in ('equity','opponent_equity','tie_probability','hand_strength','outs','pot_odds','required_equity','ev','simulation_count','timestamp','bet_scenarios'):
        assert key in result
    assert isinstance(result['equity'],float)

def test_analysis_records_reproduction_parameters():
    state = PokerTableState(hero_cards=['2c','3d'], board=['As','Ks','Qs','Js','Ts'],
                           players=[PlayerState(1),PlayerState(2)], hero_seat=1)
    result = AnalysisEngine(iterations=10000, seed=123).analyze(state).to_dict()
    assert result['simulation_seed'] == 123
    assert result['requested_simulations'] == 10000

def test_engine_requires_unambiguous_hero_seat():
    state = PokerTableState(hero_cards=['As','Kd'], players=[PlayerState(1),PlayerState(2)])
    with pytest.raises(ValueError, match='座位'):
        AnalysisEngine(iterations=10000).analyze(state)
