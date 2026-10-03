from PySide6.QtWidgets import QApplication,QPushButton
from ui.table_overlay import TableOverlay

def test_floating_panel_keeps_action_has_only_open_button_and_clears_stale_details():
    app=QApplication.instance() or QApplication([])
    panel=TableOverlay()
    panel.render({'ev':20,'range_assumed':True,'equity_details':{'win_probability':.55},
        'tie_probability':.02,'action_text':'估算可跟注 500'}, {'pot':2000,'call_amount':500})
    assert '500' in panel.label.text()
    assert '25%' in panel.details.text()
    assert [button.text() for button in panel.findChildren(QPushButton)]==['開啟視窗']
    assert not panel.details.isHidden()
    panel.invalidate('底牌未確認')
    assert '底牌未確認' in panel.label.text()
    assert '500' not in panel.details.text()
    panel.close()

def test_main_window_can_return_from_floating_mode(tmp_path):
    from ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.show()
    window.show_floating()
    assert window.isHidden() and window.overlay.isVisible()
    window.overlay.findChild(QPushButton).click()
    assert window.isVisible() and window.overlay.isHidden()
    window.close()

def test_capture_failure_clears_floating_action_and_amount(tmp_path):
    from ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.auto_active=True
    window.overlay.render({'action_text':'估算可跟注 500'}, {'pot':2000,'call_amount':500})
    window.accept_auto_unavailable(window.auto_generation,'視窗最小化')
    assert '500' not in window.overlay.label.text()
    assert window.overlay.details.text()==''
    window.close()
