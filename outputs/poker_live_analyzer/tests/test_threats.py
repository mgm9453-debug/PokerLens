from poker.threats import calculate_threats
from poker.engine import AnalysisEngine
from state.models import PokerTableState, PlayerState

def make_state(hero,board,ranges,**kwargs):
    return PokerTableState(hero_cards=hero,board=board,players=[PlayerState(0),*[PlayerState(int(s)) for s in ranges]],hero_seat=0,ranges=ranges,**kwargs)

def test_preflop_has_no_current_made_hand():
    result=calculate_threats(make_state(['As','Kd'],[],{'1':'QQ'}))
    assert result.beating_hand_types==[]
    assert '尚無當前成牌' in result.label
    assert result.combination_count==0

def test_same_category_higher_kicker_and_ties_excluded():
    result=calculate_threats(make_state(['As','Qd'],['Ah','7c','2d'],{'1':'AK AQ AJ'}))
    assert result.beating_hand_types==['一對（更高點數或踢腳）']
    assert result.counts=={'一對（更高點數或踢腳）':8}
    assert result.combination_count==8
    assert '不是出現機率' in result.label

def test_board_royal_flush_no_hand_can_win():
    result=calculate_threats(make_state(['2c','3d'],['As','Ks','Qs','Js','Ts'],{'1':'44','2':'55'}))
    assert result.beating_hand_types==[]
    assert result.combination_count==0

def test_range_blockers_union_and_hidden_cards_ignored():
    state=make_state(['As','Ad'],['Ac','Kh','Kd'],{'1':'KK','2':'KK'})
    state.players[1].hole_cards=['2s','3s']
    result=calculate_threats(state)
    assert result.beating_hand_types==['四條']
    assert result.combination_count==1
    assert result.counts['四條']==1
    assert len(result.opponent_details)==2

def test_engine_adds_threat_fields():
    result=AnalysisEngine(iterations=10000).analyze(make_state(['2c','3d'],['As','Ks','Qs','Js','Ts'],{'1':'44'})).to_dict()
    assert result['beating_hand_types']==[]
    assert result['threats_details']['legal_combination_count']==6

def test_each_street_compares_only_current_cards():
    hero=['2c','3d']
    flop=calculate_threats(make_state(hero,['4h','5s','9d'],{'1':'7c8d'}))
    assert flop.beating_hand_types==['高牌（更高點數或踢腳）']
    turn=calculate_threats(make_state(hero,['4h','5s','6c','9d'],{'1':'7c8d'}))
    assert turn.beating_hand_types==['順子（更高點數或踢腳）']
    river=calculate_threats(make_state(hero,['4h','5s','6c','9d','Kh'],{'1':'7c8d'}))
    assert river.beating_hand_types==['順子（更高點數或踢腳）']

def test_showdown_uses_revealed_hand():
    state=make_state(['As','Qd'],['Ah','7c','2d','Qc','3h'],{'1':'AA'})
    state.players[1].hole_cards=['Kc','Kd']
    assert calculate_threats(state).beating_hand_types==['三條']
    state.showdown=True
    state.street='攤牌'
    assert calculate_threats(state).beating_hand_types==[]

def test_threat_cancel():
    import pytest
    state=make_state(['As','Kd'],['2c','3d','4h'],{'1':'標準'})
    with pytest.raises(InterruptedError): calculate_threats(state,cancel=lambda:True)

def test_terminal_counts_only_when_hero_loses():
    from poker.equity import calculate_equity, EquityResult
    losing=calculate_equity(['2c','3d'],['Ah','Ac','7h','8d','9s'],['AA'],iterations=2000)
    assert losing.terminal_beating_counts=={'四條':2000}
    tied=calculate_equity(['2c','3d'],['As','Ks','Qs','Js','Ts'],['44'],iterations=2000)
    assert tied.terminal_beating_counts=={}
    assert tied.hero_equity==.5 and tied.tie_probability==1
    assert EquityResult(**losing.to_dict())==losing

def test_preflop_engine_labels_observed_terminal_threats():
    state=make_state(['As','Kd'],[],{'1':'QQ'})
    result=AnalysisEngine(iterations=2000).analyze(state)
    assert result.beating_hand_types
    assert result.threats_details['terminal_beating_counts']
    assert '終局觀察' in result.threats_details['label']
    assert '不是完整可能清單' in result.threats_details['label']
    assert result.equity==.4495
    assert result.tie_probability==.003
    assert result.equity_details['win_probability']==.448
