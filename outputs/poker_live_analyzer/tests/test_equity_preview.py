import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow


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
