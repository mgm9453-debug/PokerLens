import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_analysis_renders_values(app):
    from ui.analysis_panel import AnalysisPanel
    panel = AnalysisPanel()
    panel.render({'equity': 0.6, 'pot_odds': 0.25, 'outs': 9, 'spr': 4, 'ev': 100, 'simulation_count': 10000})
    assert '60.00%' in panel.summary.text()
    assert '25.00%' in panel.summary.text()


def test_overlay_opacity_and_visibility(app):
    from ui.table_overlay import TableOverlay
    overlay = TableOverlay()
    overlay.setWindowOpacity(0.7)
    overlay.show()
    assert overlay.isVisible()
    overlay.close()


def test_frame_can_be_displayed(app):
    import numpy as np
    from ui.roi_editor import RoiEditor
    editor = RoiEditor()
    editor.set_frame(np.zeros((100, 200, 3), dtype=np.uint8))
    assert editor.image.width() == 200


def test_window_has_demo_and_editor(app, tmp_path):
    from ui.main_window import MainWindow
    window = MainWindow(data_dir=tmp_path, auto_demo=False)
    assert window.editor.toPlainText()
    assert window.detector.version == 0
    window.close()


def test_confirmed_cards_remain_visible_when_money_blocks_analysis(app,tmp_path):
    from ui.main_window import MainWindow
    from vision.card_detector import Detection
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.auto_active=True
    token=window.auto_generation
    window.accept_auto_cards(token,Detection(('Ts','6s'),('Kd','Jd','9s'),.95,True))
    window.accept_auto_status(token,'金額不一致，拒絕更新')
    assert window.analysis.threat_layout.count()>0
    assert window.analysis.probabilities.isHidden()
    assert '黑桃十、黑桃6' in window.live_cards.text()
    assert '方塊國王、方塊傑克、黑桃9' in window.live_cards.text()
    assert window.uncertain
    window.accept_auto_hero(token,{'hero':('Ts','6s'),'board':None})
    window.accept_auto_status(token,'牌面不完整或匹配不足，等待下一幀')
    assert '黑桃十、黑桃6' in window.live_cards.text()
    window.accept_auto_hero(token,{'hero':None,'board':None})
    assert '底牌已確認' not in window.live_cards.text()
    assert window.analysis.threat_layout.count()==0
    window.close()


def test_invalid_input_does_not_update_state(app, tmp_path):
    from ui.main_window import MainWindow
    window = MainWindow(data_dir=tmp_path, auto_demo=False)
    window.editor.setPlainText('{')
    window.apply_editor()
    assert window.detector.version == 0
    assert window.uncertain
    window.close()


def test_obsolete_calculation_is_not_rendered(app, tmp_path):
    from ui.main_window import MainWindow
    window = MainWindow(data_dir=tmp_path, auto_demo=False)
    window.generation = 2
    window.accept_analysis(1, 0, object())
    assert window.result is None
    window.close()


def test_background_calculation_and_history(app, tmp_path):
    from ui.main_window import MainWindow
    from PySide6.QtTest import QTest
    window = MainWindow(data_dir=tmp_path, auto_demo=False)
    window.settings.iterations.setCurrentIndex(0)
    window.apply_editor()
    assert window.detector.version == 1
    for _ in range(300):
        QTest.qWait(20)
        if window.result:
            break
    assert window.result is not None, window.statusBar().currentMessage()
    window.apply_editor()
    assert window.detector.version == 1
    assert window.history.count() == 1
    window.replay(window.history.item(0))
    assert window.replay_mode
    assert '你現在的牌' in window.analysis.summary.text()
    window.close()
    reopened = MainWindow(data_dir=tmp_path, auto_demo=False)
    assert reopened.detector.version == 1
    reopened.close()


def test_manual_override_replaces_capture_source(app, tmp_path):
    import json
    from ui.main_window import MainWindow, demo_data
    from state.table_state import PokerTableState
    window = MainWindow(data_dir=tmp_path, auto_demo=False)
    data = demo_data()
    data.update(source='辨識', community_cards=['Ah', '8s', '3s', '4d', '5c'])
    window.detector.update(PokerTableState.from_dict(data))
    data.update(community_cards=['Ah', '8s', '3s'], street='')
    window.editor.setPlainText(json.dumps(data))
    window.apply_editor()
    assert window.detector.state.street == '翻牌'
    assert window.detector.state.source == '手動'
    window.close()


def test_invalid_state_cannot_restore_stale_result(app, tmp_path):
    from ui.main_window import MainWindow
    window = MainWindow(data_dir=tmp_path, auto_demo=False)
    window.result = {'equity': 0.9}
    window.show_error('底池不一致')
    window.return_live()
    assert window.result is None
    assert '資料不確定' in window.analysis.summary.text()
    window.close()


def test_live_snapshot_updates_numbers_and_starts_without_click(app, tmp_path):
    from ui.main_window import MainWindow
    from tests.test_live_state import inputs
    from vision.live_state import LiveStateAssembler
    window = MainWindow(data_dir=tmp_path, auto_demo=False)
    window.auto_active = True
    window.auto_generation = 7
    calls = []
    window.start_analysis = lambda: calls.append(window.detector.version)
    state = LiveStateAssembler().build(*inputs())
    window.accept_auto_table(7, state)
    assert calls == [1]
    assert '555' in window.live_numbers.text()
    assert '對手 6 人' in window.live_numbers.text()
    window.result = {'equity': .4}
    window.accept_auto_table(7, state)
    assert calls == [1]
    state['pot'] = 600
    window.accept_auto_table(7, state)
    assert calls == [1, 2]
    window.accept_auto_table(6, dict(state, pot=1000))
    assert calls == [1, 2]
    window.close()


def test_auto_waits_for_table_and_stop_cancels_retry(app,tmp_path,monkeypatch):
    from ui.main_window import MainWindow
    monkeypatch.setattr('ui.main_window.list_tables',lambda:[])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.toggle_auto()
    assert window.auto_waiting and window.auto_monitor.isActive()
    assert '等待' in window.auto_status.text()
    assert window.analyze_button.isHidden()
    assert window.clear_button.isHidden()
    assert window.demo_button.isHidden()
    assert window.simple_form.isHidden()
    window.form_edited()
    assert '按「分析」' not in window.analysis.summary.text()
    window.toggle_auto()
    assert not window.auto_waiting and not window.auto_monitor.isActive()
    window.close()


def test_live_threats_are_visible_without_expanding_details(app):
    from ui.analysis_panel import AnalysisPanel
    panel=AnalysisPanel()
    panel.render({'live':True,'street':'翻牌','spr':2,'equity':.6,'tie_probability':.04,
        'equity_details':{'win_probability':.58},'beating_hand_types':['兩對','一對（更高點數或踢腳）'],
        'threats_details':{'label':'僅比較目前公共牌'},'simulation_count':2000})
    threats=panel.threat_layout.itemAt(0).widget().text()
    assert '兩對' in threats
    assert '同牌型，但點數更大' in threats
    assert '58.0%' in panel.win_label.text()
    assert '58.0%' not in panel.summary.text()
    assert not panel.details_toggle.isChecked()

def test_probabilities_and_pictures_clear_when_data_is_stale(app):
    from ui.analysis_panel import AnalysisPanel
    panel=AnalysisPanel()
    panel.render({'live':True,'street':'翻牌','range_assumed':True,'call_amount':100,'ev':-10,
        'equity_details':{'win_probability':.58},'tie_probability':.04,
        'starting_hand':{},'threats_details':{'visual_examples':[{'category':'三條','hole_cards':['7h','7d'],
        'best_five':['7h','7d','7c','Ah','2d']}]}})
    assert '58.0%' in panel.win_label.text()
    assert '4.0%' in panel.tie_label.text()
    assert '32px' in panel.win_label.styleSheet()
    assert panel.win_label.styleSheet()!=panel.tie_label.styleSheet()
    assert '先棄牌' not in panel.summary.text()
    assert panel.threat_layout.count()==3
    assert '機會贏' not in panel.summary.text()
    assert '平手' not in panel.summary.text()
    panel.invalidate('等待新資料')
    assert panel.probabilities.isHidden()
    assert panel.threat_layout.count()==0

def test_compact_threat_tiles_start_inside_viewport(app):
    from ui.analysis_panel import AnalysisPanel
    from PySide6.QtWidgets import QWidget
    panel=AnalysisPanel()
    panel.resize(560,520)
    examples=[{'category':name,'hole_cards':['7h','7d'],'best_five':['7h','7d','7c','Ah','2d']}
        for name in ['三條','兩對','一對']]
    panel.render({'live':True,'call_amount':100,'ev':10,'hand_strength':'一對',
        'equity_details':{'win_probability':.6},'threats_details':{'visual_examples':examples}})
    panel.show()
    app.processEvents()
    tile=panel.threat_layout.itemAt(1).widget()
    point=tile.mapTo(panel.summary_scroll.viewport(),tile.rect().topLeft())
    assert 0<=point.y()<panel.summary_scroll.viewport().height()
    assert '%' not in panel.summary.text()
    assert len(panel.summary.text().splitlines())<=3
    panel.close()

@pytest.mark.parametrize('ev,expected',[(100,'可考慮入場'),(-100,'暫不投入'),(0,'邊界')])
def test_entry_displays_call_expected_value(app,ev,expected):
    from ui.analysis_panel import AnalysisPanel
    panel=AnalysisPanel()
    panel.render({'live':True,'call_amount':100,'ev':ev,'hand_strength':'一對',
        'starting_hand':{'level':'強起手牌','advice':'測試','context':'測試','source':'測試'}})
    assert expected in panel.summary.text()
    assert f'{ev:+,.0f}' in panel.summary.text()
    assert '跟注期望值' in panel.summary.text()

@pytest.mark.parametrize('call,ev,text,color',[(0,0,'過牌','#1765aa'),(100,50,'跟注 100','#087d55'),(100,-50,'棄牌','#c42b36'),(100,0,'等待確認','#9a6500')])
def test_action_is_large_and_colored(app,call,ev,text,color):
    from ui.analysis_panel import AnalysisPanel
    panel=AnalysisPanel()
    panel.render({'live':True,'call_amount':call,'ev':ev})
    assert text in panel.action_label.text()
    assert color in panel.action_label.styleSheet()
    assert '30px' in panel.action_label.styleSheet()
    panel.invalidate('讀取中')
    assert panel.action_label.text()=='等待確認'

def test_brief_hero_obstruction_is_marked_and_expires(app,tmp_path,monkeypatch):
    from ui.main_window import MainWindow
    now=[10.0]
    monkeypatch.setattr('ui.main_window.monotonic',lambda:now[0])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.auto_active=True
    token=window.auto_generation
    window.accept_auto_hero(token,{'hero':('As','Kd'),'board':()})
    now[0]+=.2
    window.accept_auto_hero(token,{'hero':None,'board':None})
    assert '最近讀到' in window.live_cards.text()
    assert '暫停決策' in window.live_cards.text()
    assert '底牌' in window.analysis.action_label.text()
    now[0]+=1
    window.accept_auto_hero(token,{'hero':None,'board':None})
    assert '最近讀到' not in window.live_cards.text()
    window.accept_auto_hero(token,{'hero':('As','Kd'),'board':()})
    window.accept_auto_hero(token,{'hero':(),'board':()})
    window.accept_auto_hero(token,{'hero':None,'board':None})
    assert '最近讀到' not in window.live_cards.text()
    window.close()

@pytest.mark.parametrize('cards',[['Ts','Th'],['Ks','Qs']])
def test_good_preflop_hand_is_visible_and_assumed_negative_ev_is_not_fold(app,cards):
    from poker.starting_hands import starting_hand_guide
    from ui.analysis_panel import AnalysisPanel
    panel=AnalysisPanel()
    panel.render({'live':True,'street':'翻牌前','range_assumed':True,'call_amount':100,'ev':-50,
        'starting_hand':starting_hand_guide(cards)})
    assert '棄牌' not in panel.action_label.text()
    assert '不入場' not in panel.action_label.text()
    assert '可考慮進場' in panel.summary.text()
    assert '位置' in panel.summary.text()

def test_amount_mismatch_keeps_numbers_visible(app):
    from ui.analysis_panel import AnalysisPanel
    panel=AnalysisPanel()
    panel.invalidate('金額不一致：底池 500、桌上下注合計 800')
    assert '500' in panel.summary.text() and '800' in panel.summary.text()

def test_live_screen_removes_old_advanced_entry_and_manual_mode_keeps_tools(app,tmp_path):
    from ui.main_window import MainWindow
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.advanced_toggle.setChecked(True)
    window.set_live_layout()
    assert window.advanced_toggle.isHidden()
    assert window.advanced_scroll.isHidden()
    assert not window.control_button.isHidden()
    window.stop_auto()
    assert not window.advanced_toggle.isHidden()
    window.close()

@pytest.mark.parametrize('cards',[['As','Ah'],['Ks','Kh'],['Qs','Qh'],['Js','Jh'],['Ts','Th'],
    ['As','Ks'],['As','Qs'],['As','Js'],['Ks','Qs'],['Ks','Js'],['Qs','Js'],['Js','Ts'],['9s','8s']])
def test_all_playable_hand_groups_follow_call_cost_instead_of_hand_name(app,cards):
    from poker.starting_hands import starting_hand_guide
    from poker.pot_odds import call_ev
    from ui.analysis_panel import AnalysisPanel
    panel=AnalysisPanel()
    for call,expected in [(100,'估算可跟注'),(1000,'跟注成本偏高')]:
        panel.render({'live':True,'street':'翻牌前','range_assumed':True,'call_amount':call,
            'ev':call_ev(.4,1000,call),'starting_hand':starting_hand_guide(cards)})
        assert expected in panel.action_label.text()
        assert '棄牌' not in panel.action_label.text()
        assert '範圍是假設' in panel.summary.text()
