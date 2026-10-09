"""回合尚未確認時保留勝率，但撤回跟注與加注指令。"""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
import pytest


@pytest.mark.parametrize('turn,word',[(False,'等待對手'),(None,'確認自身回合')])
def test_turn_gate_keeps_probability_and_hides_action(turn,word):
    from ui.analysis_panel import AnalysisPanel
    app=QApplication.instance() or QApplication([])
    panel=AnalysisPanel()
    panel.render({'live':True,'hero_turn':turn,'call_amount':300,'pot':1000,'ev':200,
        'equity_details':{'win_probability':.6},'tie_probability':.02,'facing_all_in':True})
    assert word in panel.action_label.text()
    assert '60.0%' in panel.win_label.text()
    assert '建議跟注' not in panel.action_label.text()
    panel.close()


def test_confirmed_turn_keeps_call_advice():
    from ui.analysis_panel import AnalysisPanel
    app=QApplication.instance() or QApplication([])
    panel=AnalysisPanel()
    panel.render({'live':True,'hero_turn':True,'call_amount':300,'pot':1000,'ev':200})
    assert '跟注' in panel.action_label.text()
    panel.close()


def test_buttons_disappearing_immediately_withdraw_old_advice(tmp_path):
    from types import SimpleNamespace
    from ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.auto_active=True
    window.live_hero_turn=True
    window.result={'action_text':'跟注 300'}
    try:
        amounts=SimpleNamespace(hero_turn=None,pot=1000,call_amount=300,hero_stack=9000,
            seat_bets={},seat_stacks={},field_reliable={},paused=False)
        window.accept_auto_amounts(window.auto_generation,amounts)
        assert window.result is None
        assert '確認自身回合' in window.analysis.action_label.text()
    finally:
        window.close()


def test_unrelated_unknown_bets_do_not_repeatedly_withdraw_advice(tmp_path):
    from types import SimpleNamespace
    from ui.main_window import MainWindow
    from state.models import PokerTableState
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.auto_active=True
    window.live_hero_turn=True
    window.detector.state=PokerTableState(hero_seat=0,pot=1000,call_amount=300,hero_stack=9000,
        players=[{'seat':0,'current_bet':100},{'seat':1,'current_bet':0,'bet_known':False},
            {'seat':3,'current_bet':400}])
    window.result={'action_text':'跟注 300'}
    try:
        amounts=SimpleNamespace(hero_turn=True,pot=1000,call_amount=300,hero_stack=9000,
            seat_bets={0:100,3:400},seat_stacks={},
            field_reliable={'bet_0':True,'bet_3':True},paused=False)
        window.accept_auto_amounts(window.auto_generation,amounts)
        assert window.result is not None
    finally:
        window.close()
