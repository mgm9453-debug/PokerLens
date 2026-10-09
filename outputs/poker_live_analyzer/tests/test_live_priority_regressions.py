"""修正過期資料、籌碼尺度與矩陣標色的使用者問題。"""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from ui.analysis_panel import AnalysisPanel
from ui.main_window import MainWindow
from poker.pot_odds import call_ev


@pytest.mark.parametrize('extra',[{}, {'facing_all_in':True},
    {'street':'翻牌前','starting_hand':{'level':'強起手牌','advice':'測試','context':'測試','source':'測試',
        'entry_chart':{'color':'藍色','rule':'可考慮進場'}}}])
def test_borderline_advice_is_independent_of_chip_unit(extra):
    app=QApplication.instance() or QApplication([])
    panel=AnalysisPanel()
    try:
        for multiplier in (.01,1,100000):
            panel.render({'live':True,'hero_turn':True,'pot':3*multiplier,'call_amount':multiplier,
                'ev':call_ev(.2501,3*multiplier,multiplier),**extra})
            assert any(word in panel.action_label.text() for word in ('等待確認','接近邊界','待確認'))
            assert '建議跟注' not in panel.action_label.text()
            assert '跟注參考' not in panel.sizing_label.text()
            assert '這次跟注划得來' not in panel.extra.text()
    finally:panel.close()


@pytest.mark.parametrize('equity,word',[(.6,'跟注'),(.1,'棄牌')])
def test_clear_advice_is_independent_of_chip_unit(equity,word):
    app=QApplication.instance() or QApplication([])
    panel=AnalysisPanel()
    try:
        for multiplier in (.01,1,100000):
            panel.render({'live':True,'hero_turn':True,'pot':3*multiplier,'call_amount':multiplier,
                'ev':call_ev(equity,3*multiplier,multiplier)})
            assert word in panel.action_label.text()
    finally:panel.close()


def test_sample_uncertainty_keeps_near_break_even_advice_pending():
    app=QApplication.instance() or QApplication([])
    panel=AnalysisPanel()
    try:
        panel.render({'live':True,'hero_turn':True,'pot':300000,'call_amount':100000,
            'ev':4000,'simulation_count':2000})
        assert '接近邊界' in panel.action_label.text()
    finally:panel.close()


def test_invalid_matrix_clears_red_without_losing_any_hand():
    app=QApplication.instance() or QApplication([])
    panel=AnalysisPanel();panel.dark_theme=True;panel.enable_fixed_layout()
    try:
        panel.threat_matrix.render(['8h','7h'],['9d','5d','Qs'])
        assert panel.threat_matrix.table.item(0,0).background().color().name()!='#0b9f68'
        panel.invalidate('跟注額尚未確認')
        matrix=panel.threat_matrix
        assert not matrix.isEnabled()
        assert not matrix.isHidden()
        assert matrix.table.rowCount()==matrix.table.columnCount()==13
        assert matrix.table.item(0,0).text()=='AA'
        assert matrix.table.item(12,12).text()=='22'
        assert all(matrix.table.item(r,c).background().color().name()=='#0b9f68'
            for r in range(13) for c in range(13))
        assert '尚未比較' in matrix.table.item(0,0).toolTip()
        matrix.apply_colors('#123456','#abcdef')
        assert not matrix.isEnabled()
        assert matrix.table.item(0,0).background().color().name()=='#123456'
        matrix.render(['8h','7h'],['9d','5d','Qs'])
        assert matrix.isEnabled()
        assert matrix.table.item(0,0).background().color().name()=='#abcdef'
    finally:panel.close()


def test_poll_withdraws_expired_advice_without_a_worker_failure(tmp_path,monkeypatch):
    now=[100.0]
    monkeypatch.setattr('ui.main_window.monotonic',lambda:now[0])
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    try:
        window.auto_active=True
        window.capture_last_frame=97.0
        window.live_hero_turn=True
        window.result={'live':True,'action_text':'跟注 300'}
        window.analysis.set_action('跟注 300','#087d55')
        window.overlay.render(window.result,{'pot':1000,'call_amount':300})
        generation=window.generation
        window.poll_frame()
        assert window.result is None
        assert window.generation>generation
        assert window.live_hero_turn is None
        assert '跟注 300' not in window.analysis.action_label.text()
        assert '跟注 300' not in window.overlay.label.text()
        assert '逾期' in window.analysis.issue_label.text()
        generation=window.generation
        window.poll_frame()
        assert window.generation==generation
    finally:window.close()


def test_processing_time_report_does_not_refresh_old_source(tmp_path,monkeypatch):
    monkeypatch.setattr('ui.main_window.monotonic',lambda:100.0)
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    try:
        window.auto_active=True
        window.capture_last_frame=97.0
        window.accept_auto_timing(window.auto_generation,1)
        assert window.capture_last_frame==97.0
    finally:window.close()


def test_expired_table_and_probability_cannot_restart_analysis(tmp_path,monkeypatch):
    from ui.main_window import demo_data
    monkeypatch.setattr('ui.main_window.monotonic',lambda:100.0)
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    calls=[]
    monkeypatch.setattr(window,'start_analysis',lambda:calls.append(True))
    try:
        window.auto_active=True
        window.capture_last_frame=97.0
        window.accept_auto_table(window.auto_generation,demo_data())
        assert not calls
        window.accept_equity_view(window.auto_generation,{'hero':['As','Ks'],'board':[], 'active_seats':[1]})
        assert window.partial_equity_key is None
        assert not window.workers
    finally:window.close()


@pytest.mark.parametrize('received',[float('nan'),float('inf'),101.0,99.0])
def test_invalid_or_old_frame_time_cannot_refresh_live_data(tmp_path,monkeypatch,received):
    monkeypatch.setattr('ui.main_window.monotonic',lambda:100.0)
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    try:
        window.auto_active=True
        window.capture_last_frame=99.5
        window.accept_auto_frame(window.auto_generation,received)
        assert window.capture_last_frame==99.5
    finally:window.close()


def test_fresh_source_does_not_keep_an_old_confirmed_decision(tmp_path,monkeypatch):
    now=[100.0]
    monkeypatch.setattr('ui.main_window.monotonic',lambda:now[0])
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    called=[]
    monkeypatch.setattr(window,'analysis_ready',lambda *args:called.append(True))
    try:
        window.auto_active=True
        window.capture_last_frame=100.0
        window.live_decision_time=97.0
        window.result={'live':True,'action_text':'跟注 300'}
        generation=window.generation
        window.poll_frame()
        assert window.result is None
        now[0]=100.1
        window.accept_auto_frame(window.auto_generation,100.1)
        window.accept_analysis(generation,0,object())
        assert not called
        assert window.check_live_freshness()
        assert window.result is None
    finally:window.close()
