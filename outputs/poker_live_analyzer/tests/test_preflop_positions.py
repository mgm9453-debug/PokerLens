import pytest
from poker.preflop import positions, RangeBook


def test_eight_handed_positions_and_empty_seats():
    assert positions(tuple(range(8)), 5)[0] == 'UTG'
    mapping = positions((0, 1, 3, 4, 5, 7), 4)
    assert mapping == {4: 'BTN', 5: 'SB', 7: 'BB', 0: 'UTG', 1: 'HJ', 3: 'CO'}


def test_heads_up_and_missing_button():
    assert positions((0, 7), 0) == {0: 'BTN/SB', 7: 'BB'}
    assert positions((0, 7), None) == {}
    assert positions((0, 7), 3) == {}


def chart():
    return {'format': 'MTT', 'players': 6, 'stack_bb': 40, 'ante_bb': 1,
        'position': 'UTG', 'scenario': 'open', 'open_bb': 2.3,
        'ante_type':'big_blind','payout_model':'chip_ev',
        'opponent_position': None, 'source': '測試資料', 'license': '測試專用',
        'solver': '測試專用', 'hands': {'AKs': {'raise': .7, 'call': .3}}}


def test_match_exact_conditions_preserves_mix_and_missing_hands():
    entry = chart()
    book = RangeBook([entry])
    context = {key: entry[key] for key in ('format', 'players', 'stack_bb', 'ante_bb',
        'position', 'scenario', 'open_bb', 'opponent_position', 'ante_type', 'payout_model')}
    assert book.match(context)['hands']['AKs'] == {'raise': .7, 'call': .3}
    assert '72o' not in book.match(context)['hands']
    assert book.match({**context, 'stack_bb': 39}) is None
    assert book.match({**context, 'ante_bb': None}) is None
    assert book.match({**context, 'ante_type': 'per_player'}) is None
    assert book.match({**context, 'payout_model': 'icm'}) is None
    assert RangeBook([]).match(context) is None


@pytest.mark.parametrize('frequencies', [{'raise': .8, 'call': .8}, {'raise': -1}, {'raise': float('nan')}, {'fake': 1}])
def test_reject_invalid_strategy(frequencies):
    with pytest.raises(ValueError):
        RangeBook([{**chart(), 'hands': {'AA': frequencies}}])


def test_position_tracker_preserves_folded_seats_and_resets_new_hand():
    from poker.preflop import PositionTracker
    tracker = PositionTracker()
    context = tracker.observe(('As', 'Kh'), (), (0, 1, 3, 4, 5, 7), 4, True)
    assert context['position'] == 'UTG'
    context = tracker.observe(('As', 'Kh'), (), (0, 5, 7), 4, False)
    assert context['position'] == 'UTG' and context['players'] == 6
    tracker.reset()
    assert tracker.observe(('As', 'Kh'), (), (0, 5, 7), None, False)['position'] is None


def test_position_tracker_does_not_freeze_an_incomplete_seat_list():
    from poker.preflop import PositionTracker
    tracker = PositionTracker()
    assert tracker.observe(('As', 'Kh'), (), (0, 7), 7, False)['position'] is None
    assert tracker.observe(('As', 'Kh'), (), (0, 1, 3, 4, 5, 7), 4, True)['position'] == 'UTG'
