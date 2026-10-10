from unittest.mock import patch
import pytest
from poker.engine import AnalysisEngine
from poker.equity import EquityResult
from state.models import PokerTableState


def test_amount_change_reuses_equity_but_updates_call_value():
    from ui.main_window import demo_data
    state = PokerTableState.from_dict(demo_data())
    engine = AnalysisEngine(10000)
    cache = (engine.equity_key(state), EquityResult(.6, .4, .02, .58, 10000))
    with patch('poker.engine.calculate_equity', side_effect=AssertionError('不應重抽牌')):
        first = engine.analyze(state, cached_equity=cache)
        state.pot = 30
        state.call_amount = 10
        second = engine.analyze(state, cached_equity=cache)
    assert second.equity == first.equity
    assert second.ev != first.ev
    state.hero_cards = ['Qs', 'Ks']
    with pytest.raises(ValueError, match='快取'):
        engine.analyze(state, cached_equity=cache)
