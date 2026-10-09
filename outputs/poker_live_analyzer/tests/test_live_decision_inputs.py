"""跟注資料與加注資料分開，未知下注不能假裝為零。"""
from types import SimpleNamespace
import pytest
from vision.live_state import LiveStateAssembler


def inputs():
    cards=SimpleNamespace(reliable=True,confidence=.95,hero=('Ad','Ks'),board=())
    players=SimpleNamespace(reliable=True,active_seats=(3,7),reason='')
    amounts=SimpleNamespace(reliable=False,core_reliable=True,reason='其他座位下注未確認',
        pot=1500,hero_stack=9000,call_amount=300,seat_bets={0:100,3:400,7:400},
        seat_stacks={},seats=tuple(range(8)),hero_turn=True,
        field_reliable={'pot':True,'hero_stack':True,'call_amount':True,
            'bet_0':True,'bet_3':True,'bet_7':True})
    return cards,players,amounts


def test_unknown_folded_seat_bet_does_not_block_known_call():
    state=LiveStateAssembler().build(*inputs())
    assert state['call_amount']==300
    inactive=next(player for player in state['players'] if player['seat']==1)
    assert not inactive['bet_known']
    assert state['hero_turn'] is True


def test_direct_stable_call_survives_unknown_active_bet():
    cards,players,amounts=inputs()
    amounts.seat_bets.pop(3)
    amounts.field_reliable['bet_3']=False
    state=LiveStateAssembler().build(cards,players,amounts)
    assert state['call_amount']==300
    assert not next(p for p in state['players'] if p['seat']==3)['bet_known']


@pytest.mark.parametrize('field',['pot','hero_stack','call_amount'])
def test_unknown_core_field_still_blocks_decision(field):
    cards,players,amounts=inputs()
    setattr(amounts,field,None)
    amounts.field_reliable[field]=False
    with pytest.raises(ValueError):
        LiveStateAssembler().build(cards,players,amounts)


def test_complete_active_bets_still_cross_check_button_amount():
    cards,players,amounts=inputs()
    amounts.call_amount=100
    with pytest.raises(ValueError,match='一致'):
        LiveStateAssembler().build(cards,players,amounts)
