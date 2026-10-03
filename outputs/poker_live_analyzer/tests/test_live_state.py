from types import SimpleNamespace
import pytest
from vision.live_state import LiveStateAssembler


def inputs():
    return (SimpleNamespace(reliable=True, confidence=.95, hero=('Ad','8d'), board=()),
        SimpleNamespace(reliable=True, active_seats=(2,3,4,5,6,7), reason=''),
        SimpleNamespace(reliable=True, reason='', pot=555, hero_stack=9240, call_amount=185,
            seat_bets={0:100,1:0,2:285,3:0,4:0,5:0,6:0,7:50}, seat_stacks={}))


def test_snapshot_uses_detected_players_and_unknown_effective_stack():
    assembler = LiveStateAssembler()
    cards, players, amounts = inputs()
    state = assembler.build(cards, players, amounts)
    assert sum(p['active'] for p in state['players']) == 7
    assert state['call_amount'] == 185
    assert state['effective_stack'] == 0
    assert state['players'][2]['position'] == '籌碼未讀取'
    assert assembler.build(cards, players, amounts)['hand_id'] == state['hand_id']
    assembler.waiting()
    assert assembler.build(cards, players, amounts)['hand_id'] != state['hand_id']


def test_missing_or_inconsistent_bets_never_produce_state():
    cards, players, amounts = inputs()
    amounts.seat_bets.pop(1)
    with pytest.raises(ValueError, match='下注'):
        LiveStateAssembler().build(cards, players, amounts)


def test_unstable_opponent_stack_remains_unknown():
    cards, players, amounts = inputs()
    amounts.seat_stacks = {2:99999}
    amounts.field_reliable = {'stack_2':False}
    state = LiveStateAssembler().build(cards, players, amounts)
    assert not state['players'][2]['stack_known']
    assert state['effective_stack'] == 0
    cards, players, amounts = inputs()
    amounts.call_amount = 100
    with pytest.raises(ValueError, match='一致'):
        LiveStateAssembler().build(cards, players, amounts)

def test_call_mismatch_reports_the_actual_numbers():
    cards,players,amounts=inputs()
    amounts.call_amount=100
    with pytest.raises(ValueError) as error:
        LiveStateAssembler().build(cards,players,amounts)
    assert '按鈕 100' in str(error.value)
    assert '計算差額 185' in str(error.value)
    assert '最高下注 285' in str(error.value)
