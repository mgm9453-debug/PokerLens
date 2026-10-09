"""校準設定必須能從一般設定操作，並實際傳入即時辨識。"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTabWidget


def test_settings_exposes_calibration_and_runs_its_callback(tmp_path):
    from ui.main_window import MainWindow
    from ui.control_dialog import ControlDialog
    app = QApplication.instance() or QApplication([])
    window = MainWindow(data_dir=tmp_path, auto_demo=False)
    calls = []
    try:
        dialog = ControlDialog(window.control_options, window.save_control_settings,
                               window.capture_status, window,
                               calibration_callback=lambda: calls.append(True))
        tabs = dialog.findChild(QTabWidget)
        index = next(i for i in range(tabs.count()) if tabs.tabText(i) == '辨識位置')
        tabs.setCurrentIndex(index)
        dialog.show()
        app.processEvents()
        QTest.mouseClick(dialog.calibration_button, Qt.LeftButton)
        assert calls == [True]
        dialog.close()
    finally:
        window.close()


def test_saved_profile_is_passed_to_live_worker_on_next_start(tmp_path, monkeypatch):
    from capture.calibration import CalibrationProfile, CalibrationStore
    from capture.profiles import Region
    from capture.window_capture import TableWindow
    from ui.main_window import MainWindow

    profile = CalibrationProfile({'pot': Region(.1, .2, .2, .1)}, (1128, 799)).mark_verified().lock()
    path = tmp_path / 'profiles' / 'recognition.json'
    CalibrationStore(path).save(profile)
    received = []

    class Connection:
        def connect(self, callback):
            pass

    class Worker:
        def __init__(self, handle, parent=None, diagnostic_path=None, calibration=None):
            self.handle = handle
            received.append(calibration)
            for name in ('cards', 'hero_view', 'table', 'amounts', 'view', 'equity_view',
                         'unavailable', 'status', 'timing', 'finished'):
                setattr(self, name, Connection())

        def start(self):
            pass

        def requestInterruption(self):
            pass

        def wait(self, timeout):
            return True

        def deleteLater(self):
            pass

    monkeypatch.setattr('ui.main_window.VisionWorker', Worker)
    monkeypatch.setattr('ui.main_window.list_tables', lambda: [TableWindow(77, '盲注 100/200', (0, 0, 1128, 799))])
    app = QApplication.instance() or QApplication([])
    window = MainWindow(data_dir=tmp_path, auto_demo=False)
    window.dock_beside_table = lambda table: None
    try:
        window.toggle_auto()
        assert window.auto_active
        assert received == [profile]
        assert window.calibration_path == path
    finally:
        window.close()
        app.processEvents()


def test_small_window_keeps_bet_advice_text_inside_card(tmp_path):
    from ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    window = MainWindow(data_dir=tmp_path, auto_demo=False)
    try:
        window.set_live_layout()
        window.analysis.invalidate('等待牌桌')
        window.resize(640, 900)
        window.show()
        for _ in range(8):
            app.processEvents()
        label = window.analysis.sizing_label
        assert label.height() >= label.heightForWidth(label.width())
        window.analysis.show_issue('請校準跟注金額區域：框選位置沒有可靠數字')
        app.processEvents()
        issue=window.analysis.issue_label
        assert issue.height() >= issue.heightForWidth(issue.width())
    finally:
        window.close()
        app.processEvents()


def test_calibration_failure_points_to_reachable_settings_page():
    from ui.analysis_panel import AnalysisPanel
    app = QApplication.instance() or QApplication([])
    panel = AnalysisPanel()
    panel.enable_fixed_layout()
    panel.show_issue('請校準跟注金額區域：框選位置沒有可靠數字')
    assert '調整設定' in panel.issue_label.text()
    assert '辨識位置' in panel.issue_label.text()
    assert '重新找牌桌' not in panel.issue_label.text()
    panel.close()


def _fake_live_worker(monkeypatch):
    from capture.window_capture import TableWindow
    instances=[]

    class Connection:
        def __init__(self):
            self.callbacks=[]

        def connect(self,callback):
            self.callbacks.append(callback)

        def emit(self):
            for callback in self.callbacks:
                callback()

    class Worker:
        def __init__(self,handle,parent=None,diagnostic_path=None,calibration=None):
            self.handle=handle
            self.calibration=calibration
            self.interrupted=False
            self.running=True
            self.finished=Connection()
            for name in ('cards','hero_view','table','amounts','view','equity_view','unavailable','status','timing'):
                setattr(self,name,Connection())
            instances.append(self)

        def start(self):
            pass

        def isRunning(self):
            return self.running

        def requestInterruption(self):
            self.interrupted=True

        def wait(self,timeout):
            return True

        def deleteLater(self):
            pass

    monkeypatch.setattr('ui.main_window.VisionWorker',Worker)
    monkeypatch.setattr('ui.main_window.list_tables',lambda:[TableWindow(77,'盲注 100/200',(0,0,1128,799))])
    return instances


def test_calibration_change_restarts_after_old_reader_stops(tmp_path,monkeypatch):
    from capture.calibration import CalibrationProfile,CalibrationStore
    from capture.profiles import Region
    from ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    workers=_fake_live_worker(monkeypatch)
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.dock_beside_table=lambda table:None
    try:
        window.toggle_auto()
        old_token=window.auto_generation
        profile=CalibrationProfile({'pot':Region(.2,.3,.2,.1)},(1128,799)).mark_verified().lock()
        CalibrationStore(window.calibration_path).save(profile)
        window.poll_control_settings()
        assert workers[0].interrupted
        assert len(workers)==1
        assert window.result is None
        issue=window.analysis.issue_label.text()
        window.accept_auto_status(old_token,'過期資料')
        assert window.analysis.issue_label.text()==issue
        workers[0].finished.emit()
        assert len(workers)==2
        assert workers[1].calibration==profile
        assert window.auto_active
    finally:
        window.close()
        app.processEvents()


def test_corrupt_calibration_cannot_leave_auto_mode_stuck(tmp_path,monkeypatch):
    from ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    workers=_fake_live_worker(monkeypatch)
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    try:
        window.calibration_path.write_text('{毀損資料',encoding='utf-8')
        window.toggle_auto()
        assert not workers
        assert not window.auto_active
        assert not window.auto_waiting
        assert not window.auto_watch
        assert '辨識位置' in window.analysis.issue_label.text()
        assert window.auto_button.text()=='開啟自動辨識'
    finally:
        window.close()
        app.processEvents()


def test_stopping_during_calibration_restart_does_not_restart_again(tmp_path,monkeypatch):
    from ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    workers=_fake_live_worker(monkeypatch)
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.dock_beside_table=lambda table:None
    try:
        window.toggle_auto()
        window.calibration_saved()
        assert window.stop_auto()
        workers[0].finished.emit()
        assert len(workers)==1
        assert not window.auto_active
        assert not window.auto_watch
    finally:
        window.close()
        app.processEvents()


def test_failed_reader_exit_returns_to_startable_state(tmp_path,monkeypatch):
    from ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    workers=_fake_live_worker(monkeypatch)
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.dock_beside_table=lambda table:None
    try:
        window.toggle_auto()
        workers[0].running=False
        workers[0].finished.emit()
        assert not window.auto_active
        assert not window.auto_watch
        assert window.vision_worker is None
        assert window.auto_button.text()=='開啟自動辨識'
    finally:
        window.close()
        app.processEvents()


def test_standalone_settings_waits_for_calibration_thread_before_closing(tmp_path):
    import threading
    from time import monotonic
    from types import SimpleNamespace
    import numpy as np
    from control_settings import validate
    from ui.control_dialog import ControlDialog
    from ui.calibration_dialog import CalibrationDialog
    app=QApplication.instance() or QApplication([])
    entered=threading.Event()
    release=threading.Event()
    class Source:
        def open(self):
            pass
        def read(self):
            entered.set()
            release.wait(2)
            return np.full((500,1000,3),90,np.uint8)
        def close(self):
            pass
    panel=ControlDialog(validate({}),lambda values:None,lambda:'等待牌桌')
    dialog=CalibrationDialog(tmp_path/'recognition.json',lambda:None,panel,
        table_provider=lambda:[SimpleNamespace(handle=11,title='盲注 10/20')],
        capture_factory=lambda handle:Source())
    panel.calibration_dialog=dialog
    panel.show()
    dialog.show()
    try:
        deadline=monotonic()+2
        while not entered.is_set() and monotonic()<deadline:
            app.processEvents()
            QTest.qWait(5)
        assert entered.is_set()
        panel.close()
        assert panel.isVisible()
        assert dialog.worker.isInterruptionRequested()
        release.set()
        deadline=monotonic()+2
        while panel.isVisible() and monotonic()<deadline:
            app.processEvents()
            QTest.qWait(5)
        assert not panel.isVisible()
        assert dialog.worker is None
    finally:
        release.set()
        deadline=monotonic()+2
        while dialog.worker is not None and monotonic()<deadline:
            app.processEvents()
            QTest.qWait(5)
        dialog.close()
        panel.close()
