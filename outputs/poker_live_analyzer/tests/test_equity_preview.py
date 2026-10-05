import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow


def test_probability_preview_keeps_its_action_and_missing_amount_reason(tmp_path):
    from ui.analysis_panel import AnalysisPanel
    app=QApplication.instance() or QApplication([])
    panel=AnalysisPanel();panel.dark_theme=True;panel.enable_fixed_layout()
    try:
        panel.invalidate('缺少必要金額，等待辨識：跟注額')
        panel.render({'live':True,'equity_only':True,'hero_cards':['As','Ks'],
            'community_cards':[],'equity':.6,'equity_details':{'win_probability':.58},
            'tie_probability':.02,'opponents':1})
        assert '58.0%' in panel.win_label.text()
        assert '勝率已估算' in panel.action_label.text()
        assert '等待資料確認' in panel.action_label.text()
        assert '跟注額' in panel.issue_label.text()
        assert '假設對手範圍' in panel.summary.text()
        assert '過牌' not in panel.action_label.text()
        assert not panel.action_label.isHidden()
        panel.render({'live':True,'hero_cards':['As','Ks'],'community_cards':[],
            'call_amount':500,'pot':2000,'ev':300,'range_assumed':True,
            'equity_details':{'win_probability':.58},'tie_probability':.02})
        assert '跟注 500' in panel.action_label.text()
        assert panel.last_issue_message==''
        panel.render({'live':True,'equity_only':True,'hero_cards':['As','Ks'],
            'community_cards':[],'equity_details':{'win_probability':.58}})
        assert '跟注額' not in panel.issue_label.text()
    finally:panel.close()


def test_money_failure_keeps_card_only_probability(tmp_path):
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.auto_active=True
    observation={'hero':['As','Ks'],'board':['Ah','8s','3s'],'active_seats':[2]}
    window.accept_equity_view(window.auto_generation,observation)
    for worker in list(window.workers): worker.wait(5000)
    app.processEvents()
    window.accept_auto_status(window.auto_generation,'缺少必要金額，等待辨識：跟注額')
    assert '%' in window.analysis.win_label.text()
    assert not window.analysis.probabilities.isHidden()
    assert '等待資料確認' in window.analysis.action_label.text()
    window.accept_auto_unavailable(window.auto_generation,'牌桌已最小化')
    assert '更新中' in window.analysis.win_label.text()
    assert '%' not in window.analysis.win_label.text()
    window.close()


def test_table_selection_uses_requested_handle(tmp_path,monkeypatch):
    from capture.window_capture import TableWindow
    app=QApplication.instance() or QApplication([])
    tables=[TableWindow(10,'第一桌 盲注 50/100',(0,0,1000,700)),
        TableWindow(20,'第二桌 盲注 50/100',(0,0,1000,700))]
    monkeypatch.setattr('ui.main_window.list_tables',lambda:tables)
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.refresh_table_choices()
    window.table_choice.setCurrentIndex(window.table_choice.findData(20))
    assert window.selected_table(tables).handle==20
    window.close()
