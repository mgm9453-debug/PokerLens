"""更新介面的背景工作、錯誤狀態及關閉流程。"""
import time
import json
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QLabel, QFileDialog
from ui.update_dialog import UpdateController

def test_release_message_is_plain_and_clear(tmp_path):
    from ui.update_dialog import UpdateDialog
    from PySide6.QtCore import Qt
    app = QApplication.instance() or QApplication([])
    dialog = UpdateDialog(SimpleNamespace(version='1.0.2', notes='<b>新版說明</b>'), '1.0.1')
    text = '\n'.join(label.text() for label in dialog.findChildren(QLabel))
    assert '發現新版本 v1.0.2' in text
    assert '目前版本：v1.0.1' in text
    assert dialog.later.text() == '稍後更新'
    assert dialog.notes.textFormat() == Qt.TextFormat.PlainText
    dialog.close()


def wait(app, predicate):
    limit = time.monotonic() + 3
    while not predicate() and time.monotonic() < limit:
        app.processEvents()
        time.sleep(.005)
    app.processEvents()
    assert predicate()


class Client:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def check(self):
        if self.error:
            raise OSError(self.error)
        return self.result

    def download(self, release, progress):
        progress(50, 100)
        return '下載目錄'


def controller(tmp_path, client):
    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    value = UpdateController(parent, tmp_path/'product.json', tmp_path, tmp_path, client)
    return app, parent, value


def test_idle_and_unconfigured(tmp_path):
    app, parent, value = controller(tmp_path, None)
    (tmp_path/'product.json').write_text('{}')
    page = value.create_about_page()
    assert '尚未檢查' in value.status_text
    value.check()
    assert value.status_text == '尚未設定更新來源。'
    assert value.shutdown()
    page.deleteLater()
    parent.close()


def test_offline_is_failure_and_latest_is_success(tmp_path):
    app, parent, value = controller(tmp_path, Client(error='離線'))
    value.check()
    wait(app, lambda: value.worker is None)
    assert '失敗' in value.status_text
    assert '最新' not in value.status_text
    value.client = Client()
    value.check()
    wait(app, lambda: value.worker is None)
    assert '最新版本' in value.status_text
    parent.close()


def test_download_progress_and_handoff(tmp_path):
    release = SimpleNamespace(version='2.0.0', notes='修正問題')
    app, parent, value = controller(tmp_path, Client(result=release))
    emitted = []
    value.install_requested.connect(lambda *args: emitted.append(args))
    value.check()
    wait(app, lambda: value.worker is None)
    value.download()
    wait(app, lambda: value.worker is None)
    assert value.dialog.progress.value() == 50
    assert emitted[0][0] is release
    assert emitted[0][1].name == '下載目錄'
    assert value.shutdown()
    parent.close()


def test_close_cancels_worker_without_destroying_running_thread(tmp_path):
    class Slow(Client):
        def check(self):
            time.sleep(.05)
            return SimpleNamespace(version='2.0.0')
    app, parent, value = controller(tmp_path, Slow())
    value.startup_check()
    app.processEvents()
    assert not value.shutdown()
    wait(app, lambda: value.worker is None)
    assert value.dialog is None
    assert value.shutdown()
    parent.close()


def test_download_cancel_keeps_gui_responsive_and_skips_install(tmp_path):
    class SlowDownload(Client):
        def download(self, release, progress):
            for index in range(30):
                time.sleep(.01)
                progress(index, 30)
            return '下載目錄'
    app, parent, value = controller(tmp_path, SlowDownload(SimpleNamespace(version='2.0.0')))
    emitted = []
    value.install_requested.connect(lambda *args: emitted.append(args))
    value.check()
    wait(app, lambda: value.worker is None)
    value.download()
    app.processEvents()
    assert value.worker is not None
    value.dialog.reject()
    wait(app, lambda: value.worker is None)
    assert not emitted
    assert value.status_text == '更新已取消。'
    parent.close()


def test_import_request_preserves_existing_data_and_source(tmp_path):
    app, parent, value = controller(tmp_path/'current', Client())
    old = tmp_path/'old'
    (old/'data').mkdir(parents=True)
    (old/'profiles').mkdir()
    (old/'data/control_settings.json').write_text('{"refresh_ms": 500}')
    (old/'data/history.sqlite3').write_bytes('舊版歷史'.encode())
    (old/'profiles/table.json').write_text('{}')
    current = value.user_data
    current.mkdir()
    (current/'history.sqlite3').write_bytes('目前歷史'.encode())
    (current/'control_settings.json').write_text('{"refresh_ms": 100}')
    assert value.queue_import(old/'data') == old.resolve()
    assert json.loads((current/'migration_request.json').read_text()) == {'source':str(old.resolve())}
    assert (current/'history.sqlite3').read_bytes() == '目前歷史'.encode()
    assert (current/'control_settings.json').read_text() == '{"refresh_ms": 100}'
    assert (old/'data/history.sqlite3').read_bytes() == '舊版歷史'.encode()
    parent.close()


def test_import_button_saves_request_and_displays_next_start(tmp_path, monkeypatch):
    app, parent, value = controller(tmp_path/'current', Client())
    old = tmp_path/'old'
    old.mkdir()
    (old/'control_settings.json').write_text('{}')
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(old))
    page = value.create_about_page()
    button = next(button for button in page.findChildren(QPushButton) if '匯入舊版' in button.text())
    button.click()
    assert (value.user_data/'migration_request.json').is_file()
    assert any('已安排匯入，下次啟動生效' in label.text() for label in page.findChildren(QLabel))
    assert not (value.user_data/'control_settings.json').exists()
    parent.close()
