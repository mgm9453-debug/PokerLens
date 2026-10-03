"""以背景執行緒檢查及下載經驗證的更新。"""
import json
import logging
import threading
from pathlib import Path
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton,
                              QDialogButtonBox, QProgressBar, QWidget, QFileDialog)
from .fonts import interface_font


class _UpdateThread(QThread):
    result = Signal(object)
    failed = Signal(str)
    progress = Signal(object, object)

    def __init__(self, client, release=None, parent=None):
        super().__init__(parent)
        self.client, self.release = client, release
        self.cancelled = threading.Event()

    def run(self):
        try:
            if self.cancelled.is_set():
                return
            value = (self.client.check() if self.release is None else
                     self.client.download(self.release, self.report_progress))
            if not self.cancelled.is_set():
                self.result.emit(value)
        except Exception as error:
            if not self.cancelled.is_set():
                self.failed.emit(str(error))

    def report_progress(self, received, total):
        if self.cancelled.is_set():
            raise RuntimeError('使用者取消下載')
        self.progress.emit(received, total)


class UpdateDialog(QDialog):
    download_requested = Signal()

    def __init__(self, release, current_version, parent=None):
        super().__init__(parent)
        self.setFont(interface_font())
        self.setWindowTitle('有可用更新')
        self.resize(460, 280)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f'發現新版本 v{release.version}\n目前版本：v{current_version}\n最新版本：v{release.version}'))
        notes = getattr(release, 'notes', '')
        if not notes and getattr(release, 'manifest', None):
            try:
                manifest = json.loads(release.manifest)
                notes = manifest.get('notes') or manifest.get('release_notes') or ''
            except (ValueError, TypeError):
                notes = ''
        label = QLabel(notes or '新版更新內容請參閱發布頁面。')
        self.notes = label
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.status = QLabel('下載完成後將關閉程式並啟動更新工具。')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.buttons = QDialogButtonBox()
        self.now = self.buttons.addButton('立即更新', QDialogButtonBox.AcceptRole)
        self.later = self.buttons.addButton('稍後更新', QDialogButtonBox.RejectRole)
        self.now.clicked.connect(self.download_requested)
        self.later.clicked.connect(self.reject)
        layout.addWidget(self.buttons)


class UpdateController(QObject):
    install_requested = Signal(object, object)
    status_changed = Signal(str)
    idle = Signal()

    def __init__(self, parent, product_path, install_root, user_data, client=None):
        super().__init__(parent)
        self.product_path = Path(product_path)
        self.client = client
        self.install_root, self.user_data = Path(install_root), Path(user_data)
        self.worker = None
        self.dialog = None
        self.release = None
        self.closing = False
        self.startup_checked = False
        self.status_text = '尚未檢查更新。'
        self.pages = []
        from version import CURRENT_VERSION
        self.current_version = CURRENT_VERSION

    def create_about_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(f'PokerLens\n開發者：天選之仁\n目前版本：v{self.current_version}'))
        status = QLabel(self.status_text)
        status.setWordWrap(True)
        layout.addWidget(status)
        button = QPushButton('檢查更新')
        button.clicked.connect(lambda: self.check(manual=True))
        layout.addWidget(button)
        import_button = QPushButton('匯入舊版設定與歷史')
        import_button.clicked.connect(self.request_import)
        layout.addWidget(import_button)
        import_status = QLabel('選擇舊版程式或資料資料夾；匯入將於下次啟動生效，原始檔案與現有資料均保留。')
        import_status.setWordWrap(True)
        layout.addWidget(import_status)
        import_button.setProperty('import_status', import_status)
        layout.addStretch()
        self.pages.append((page, status, button))
        page.destroyed.connect(lambda: self._remove_page(page))
        return page

    def request_import(self):
        source = QFileDialog.getExistingDirectory(self.parent(), '選擇舊版程式或資料資料夾')
        if not source:
            return
        button = self.sender()
        label = button.property('import_status') if button else None
        try:
            self.queue_import(source)
            message = '已安排匯入，下次啟動生效。原始檔案與現有設定及歷史不會被覆寫。'
        except (ValueError, OSError) as error:
            message = f'無法安排匯入：{error}'
        if label:
            label.setText(message)

    def queue_import(self, source):
        """只保存下一次啟動的匯入請求，不碰執行中的資料庫。"""
        source = Path(source).resolve()
        if not source.is_dir():
            raise ValueError('找不到舊版資料夾')
        if source.name.casefold() == 'data' and (source.parent/'profiles').is_dir():
            source = source.parent
        legacy = source/'data' if (source/'data').is_dir() else source
        if not any((legacy/name).is_file() for name in ('control_settings.json', 'history.sqlite3')) and not any((source/'profiles').glob('*.json')):
            raise ValueError('此資料夾沒有可匯入的設定、歷史或區域檔案')
        from updates.storage import atomic_json
        atomic_json(self.user_data/'migration_request.json', {'source':str(source)})
        return source

    def _remove_page(self, page):
        self.pages = [item for item in self.pages if item[0] is not page]

    def _status(self, text):
        self.status_text = text
        for _, label, button in self.pages:
            label.setText(text)
            button.setEnabled(self.worker is None and not self.closing)
        self.status_changed.emit(text)

    def startup_check(self):
        if self.startup_checked:
            return
        self.startup_checked = True
        QTimer.singleShot(0, lambda: self.check(manual=False))

    def check(self, manual=True):
        if self.worker is not None or self.closing:
            return
        try:
            if self.client is None:
                product = json.loads(self.product_path.read_text(encoding='utf-8'))
                if not product.get('github_repository') or not product.get('update_public_key'):
                    self._status('尚未設定更新來源。')
                    return
                from updates.client import UpdateClient
                self.client = UpdateClient(self.product_path, self.install_root, self.user_data)
        except Exception as error:
            self._status(f'檢查失敗：{error}')
            return
        self._start(None, self._checked)
        self._status('正在檢查更新…')

    def _start(self, release, callback):
        worker = _UpdateThread(self.client, release, self)
        self.worker = worker
        worker.result.connect(callback)
        worker.failed.connect(self._failed)
        worker.progress.connect(self._progress)
        worker.finished.connect(lambda: self._finished(worker))
        worker.start()

    def _finished(self, worker):
        if self.worker is worker:
            self.worker = None
        worker.deleteLater()
        if worker.cancelled.is_set() and not self.closing:
            self.status_text = '更新已取消。'
        self._status(self.status_text)
        self.idle.emit()

    def _checked(self, release):
        if self.closing:
            return
        if release is None:
            self._status('目前已是最新版本。')
            return
        self.release = release
        self._status(f'可更新至 {release.version}。')
        self.dialog = UpdateDialog(release, self.current_version, self.parent())
        self.dialog.download_requested.connect(self.download)
        self.dialog.rejected.connect(self.cancel)
        self.dialog.show()

    def download(self):
        if self.worker is not None or self.closing or self.release is None:
            return
        self.dialog.now.setEnabled(False)
        self.dialog.later.setText('取消下載')
        self.dialog.progress.show()
        self._start(self.release, self._downloaded)
        self._status('正在下載更新…')

    def _progress(self, received, total):
        if self.dialog and not self.closing:
            self.dialog.progress.setRange(0, 100 if total else 0)
            if total:
                self.dialog.progress.setValue(min(100, int(received * 100 / total)))
            self.dialog.status.setText(f'已下載 {received:,} / {total:,} 位元組')

    def _failed(self, message):
        logging.error('更新檢查或下載失敗：%s', message)
        self._status(f'更新失敗：{message}')
        if self.dialog:
            self.dialog.status.setText(self.status_text)
            self.dialog.now.setEnabled(True)

    def _downloaded(self, path):
        if not self.closing:
            self._status('下載完成，正在交由更新工具處理。')
            if self.dialog:
                self.dialog.accept()
            self.install_requested.emit(self.release, Path(path))

    def cancel(self):
        if self.worker:
            self.worker.cancelled.set()
            self._status('正在取消下載…')

    def shutdown(self):
        """要求取消；傳回是否已停止，呼叫端可等待 idle 再關閉視窗。"""
        self.closing = True
        if self.dialog:
            self.dialog.reject()
        if self.worker:
            self.worker.cancelled.set()
            return False
        return True
