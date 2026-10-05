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


def test_auto_docking_does_not_override_manual_floating_mode(tmp_path,monkeypatch):
    from ui.main_window import MainWindow
    from capture.window_capture import TableWindow
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    try:
        window.show();window.show_floating();window.auto_active=True
        monkeypatch.setattr('ui.window_placement.table_screen',lambda *_: (_ for _ in ()).throw(AssertionError('收合後不應自動排版主視窗')))
        window.dock_beside_table(TableWindow(99,'盲注 50/100',(0,0,1128,799)))
        assert window.isHidden() and window.overlay.isVisible()
    finally:window.close()


def test_instance_connection_restores_main_and_acknowledges(tmp_path):
    import time
    from PySide6.QtNetwork import QLocalSocket
    from instance_guard import InstanceGuard
    from ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    guard=InstanceGuard(tmp_path);assert guard.acquire();guard.bind(window)
    socket=QLocalSocket()
    try:
        window.show();window.show_floating()
        socket.connectToServer(guard.name);assert socket.waitForConnected(500)
        deadline=time.monotonic()+1
        while time.monotonic()<deadline and not socket.bytesAvailable():app.processEvents()
        assert bytes(socket.readAll())==b'shown'
        assert window.isVisible() and window.overlay.isHidden()
    finally:
        socket.close();guard.server.newConnection.disconnect();guard.server.close();guard.lock.unlock();window.close()
        app.processEvents()


def test_native_launcher_connection_restores_hidden_window(tmp_path):
    import os,time
    if os.name!='nt':return
    from concurrent.futures import ThreadPoolExecutor
    from instance_guard import InstanceGuard
    from launcher import request_activation
    from ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    guard=InstanceGuard(tmp_path);assert guard.acquire();guard.bind(window)
    try:
        window.show();window.show_floating()
        with ThreadPoolExecutor(1) as executor:
            future=executor.submit(request_activation,tmp_path)
            deadline=time.monotonic()+2
            while not future.done() and time.monotonic()<deadline:
                app.processEvents();time.sleep(.005)
            assert future.result(timeout=1)
        assert window.isVisible() and window.overlay.isHidden()
    finally:
        guard.server.newConnection.disconnect();guard.server.close();guard.lock.unlock();window.close()
        app.processEvents()


def test_native_launcher_missing_connection_is_not_success(tmp_path):
    from launcher import request_activation
    assert not request_activation(tmp_path)


def test_successful_main_close_requests_application_exit(tmp_path,monkeypatch):
    from ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    calls=[]
    monkeypatch.setattr(app,'quit',lambda:calls.append(True))
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.show();window.close();app.processEvents()
    assert calls==[True]
