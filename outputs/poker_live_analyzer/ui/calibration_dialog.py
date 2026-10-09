"""在指定牌桌的定格畫面校準，實際讀取通過後才允許鎖定。"""
import asyncio
from contextlib import nullcontext
from time import monotonic

from PySide6.QtCore import Qt, QRectF, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QHeaderView,
                              QLabel, QPushButton, QTableWidget, QTableWidgetItem,
                              QVBoxLayout, QWidget)

from capture.calibration import CalibrationProfile, CalibrationStore, region_labels
from capture.graphics_capture import GraphicsWindowCapture
from capture.profiles import TableProfile
from capture.window_capture import list_tables
from .fonts import interface_font
from .roi_editor import RoiEditor
from .theme import COLORS, STYLE


class CalibrationCanvas(RoiEditor):
    """沿用影像顯示座標，鎖定後停止接受拖曳。"""
    def __init__(self):
        super().__init__()
        self.locked = False
        self.labels = region_labels()
        self.setAccessibleName('牌桌校準預覽')
        self.setToolTip('先選擇右側欄位，再拖曳框住整個文字、牌面或牌背。')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(COLORS['secondary']))
        rect = self.image_rect()
        if self.image.isNull():
            painter.setPen(QColor(COLORS['text']))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             '等待牌桌預覽\n開啟牌桌後，按「更新預覽」')
            return
        painter.drawImage(rect, self.image)
        for name, region in self.profile.regions.items():
            selected = name == self.target
            painter.setPen(QPen(QColor(COLORS['gold'] if selected else '#8DDCB5'), 3 if selected else 2))
            box = QRectF(rect.x() + region.x * rect.width(), rect.y() + region.y * rect.height(),
                         region.width * rect.width(), region.height * rect.height())
            painter.drawRect(box)
            label = self.labels.get(name, '自訂區域')
            text_box = painter.fontMetrics().boundingRect(label)
            label_box = QRectF(box.x(), max(rect.top(), box.y() - text_box.height() - 6),
                               text_box.width() + 12, text_box.height() + 6)
            painter.fillRect(label_box, QColor(COLORS['card']))
            painter.drawText(label_box, Qt.AlignmentFlag.AlignCenter, label)
        if self.start is not None and self.end is not None:
            painter.setPen(QPen(QColor(COLORS['gold']), 2))
            painter.drawRect(QRectF(self.start, self.end).normalized())

    def mousePressEvent(self, event):
        if not self.locked and not self.image.isNull():
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self.locked:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.locked:
            self.start = self.end = None
            return
        if self.start is not None:
            # 放開的位置也要裁切，避免未收到移動事件時漏掉框選。
            super().mouseMoveEvent(event)
        super().mouseReleaseEvent(event)


class _CalibrationWorker(QThread):
    preview = Signal(int, object)
    validated = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, token, handle, capture_factory, profile=None, validator=None, timeout=30.0, parent=None):
        super().__init__(parent)
        self.token, self.handle = token, handle
        self.capture_factory = capture_factory
        self.profile, self.validator = profile, validator
        self.timeout = timeout

    async def _validate(self, frames):
        task = asyncio.create_task(self.validator(self.profile, frames))
        deadline = monotonic() + self.timeout
        try:
            while not task.done():
                if self.isInterruptionRequested():
                    raise asyncio.CancelledError()
                if monotonic() >= deadline:
                    raise TimeoutError('讀取驗證逾時，請重試')
                await asyncio.wait({task}, timeout=.04)
            return await task
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    def run(self):
        source = None
        try:
            if self.isInterruptionRequested():
                return
            source = self.capture_factory(self.handle)
            source.open()
            frames, last_received = [], None
            deadline = monotonic() + min(self.timeout, 8.0)
            required = 1 if self.profile is None else 3
            while len(frames) < required:
                if self.isInterruptionRequested():
                    return
                if monotonic() >= deadline:
                    raise TimeoutError('等待牌桌的新影格逾時，請確認牌桌仍在更新後重試')
                # 影像與更新時間一起讀取，避免新幀剛好到達造成時間與畫面不配對。
                with getattr(source, '_condition', nullcontext()):
                    frame = source.read()
                    received = getattr(source, '_received', None)
                if self.isInterruptionRequested():
                    return
                if monotonic() >= deadline:
                    raise TimeoutError('等待牌桌的新影格逾時，請確認牌桌仍在更新後重試')
                # 原生擷取保存最新影格；同一更新時間不能充作多幀一致性。
                if received is not None and received == last_received:
                    self.msleep(20)
                    continue
                last_received = received
                if self.profile is not None:
                    size = (frame.shape[1], frame.shape[0])
                    if size != tuple(self.profile.reference_size):
                        raise ValueError('牌桌尺寸已變更，請更新預覽並重新驗證')
                frames.append(frame.copy())
            if self.profile is None:
                self.preview.emit(self.token, frames[0])
            else:
                value = asyncio.run(self._validate(frames))
                if not self.isInterruptionRequested():
                    self.validated.emit(self.token, value)
        except asyncio.CancelledError:
            pass
        except Exception as error:
            if not self.isInterruptionRequested():
                detail = str(error)
                if not any('\u4e00' <= char <= '\u9fff' for char in detail):
                    detail = '無法取得可靠的牌桌資料，請確認牌桌後重試'
                self.failed.emit(self.token, detail)
        finally:
            if source is not None:
                try:
                    source.close()
                except Exception:
                    pass


class CalibrationDialog(QDialog):
    def __init__(self, profile_path, on_saved, parent=None, initial_handle=None, *,
                 capture_factory=None, table_provider=None, validator=None, validation_timeout=30.0):
        super().__init__(parent)
        self.setFont(interface_font())
        self.setStyleSheet(STYLE)
        self.setWindowTitle('辨識位置校準')
        self.resize(1100, 760)
        self.store = CalibrationStore(profile_path)
        self.on_saved = on_saved
        self.capture_factory = capture_factory or GraphicsWindowCapture
        self.table_provider = table_provider or list_tables
        if validator is None:
            from vision.calibrated_detection import validate_calibration
            validator = validate_calibration
        self.validator = validator
        self.validation_timeout = validation_timeout
        self.worker = None
        self._generation = 0
        self._selected_handle = None
        self._initial_handle = initial_handle
        self._tables_initialized = False
        self._preview_pending = False
        self._pending_close = False
        self._closing_result = QDialog.DialogCode.Rejected
        load_error = ''
        try:
            self.profile = self.store.load() or CalibrationProfile({}, (1128, 799))
        except (ValueError, OSError) as error:
            self.profile = CalibrationProfile({}, (1128, 799))
            load_error = f'原校準設定無法載入，請重新校準：{error}'
        self._build_ui()
        self._refresh_regions()
        self.status.setText(load_error or ('已載入鎖定設定；按「重新校準」才能修改。' if self.profile.locked else
                                          '選擇問題欄位並框選；其他欄位沿用自動定位。'))
        self._sync_canvas()
        self._update_buttons()
        QTimer.singleShot(0, self.refresh_tables)

    @property
    def selected_handle(self):
        """回傳本次選擇的牌桌，不將視窗控制代碼存入設定。"""
        return self.table_combo.currentData()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        title = QLabel('辨識位置')
        title.setObjectName('sectionTitle')
        layout.addWidget(title)
        instruction = QLabel('選牌桌 → 框選有問題的欄位 → 驗證並鎖定。預覽會定格，更新時才換畫面。')
        instruction.setWordWrap(True)
        layout.addWidget(instruction)
        table_row = QHBoxLayout()
        table_row.addWidget(QLabel('牌桌視窗'))
        self.table_combo = QComboBox()
        self.table_combo.setAccessibleName('選擇牌桌視窗')
        table_row.addWidget(self.table_combo, 1)
        self.preview_button = QPushButton('更新預覽')
        self.preview_button.clicked.connect(self.refresh_tables)
        table_row.addWidget(self.preview_button)
        layout.addLayout(table_row)
        middle = QHBoxLayout()
        self.canvas = CalibrationCanvas()
        middle.addWidget(self.canvas, 3)
        side = QWidget()
        side.setMinimumWidth(280)
        side.setMaximumWidth(360)
        controls = QVBoxLayout(side)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addWidget(QLabel('牌桌版型'))
        self.layout_combo = QComboBox()
        self.layout_combo.addItem('八人桌', 8)
        self.layout_combo.addItem('六人桌', 6)
        self.layout_combo.setCurrentIndex(self.layout_combo.findData(self.profile.seat_layout))
        controls.addWidget(self.layout_combo)
        controls.addWidget(QLabel('要校準的欄位'))
        self.region_combo = QComboBox()
        self.region_combo.setAccessibleName('選擇框選欄位')
        controls.addWidget(self.region_combo)
        self.region_hint = QLabel()
        self.region_hint.setWordWrap(True)
        controls.addWidget(self.region_hint)
        self.clear_region_button = QPushButton('此欄位恢復自動定位')
        self.clear_region_button.clicked.connect(self.clear_region)
        controls.addWidget(self.clear_region_button)
        controls.addWidget(QLabel('已框選欄位與驗證結果'))
        self.results = QTableWidget(0, 2)
        self.results.setHorizontalHeaderLabels(['欄位', '讀取結果'])
        self.results.verticalHeader().hide()
        self.results.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.results.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results.setWordWrap(True)
        self.results.itemSelectionChanged.connect(self._result_selected)
        controls.addWidget(self.results, 1)
        middle.addWidget(side, 1)
        layout.addLayout(middle, 1)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setAccessibleName('校準操作狀態')
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.validate_button = QPushButton('驗證讀取')
        self.save_button = QPushButton('鎖定並儲存')
        self.unlock_button = QPushButton('重新校準')
        self.automatic_button = QPushButton('使用自動定位')
        self.close_button = QPushButton('關閉')
        for button in (self.validate_button, self.save_button, self.unlock_button, self.automatic_button, self.close_button):
            button.setMinimumHeight(44)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.table_combo.currentIndexChanged.connect(self._table_changed)
        self.layout_combo.currentIndexChanged.connect(self._layout_changed)
        self.region_combo.currentIndexChanged.connect(self._region_changed)
        self.canvas.selected.connect(self._canvas_selected)
        self.validate_button.clicked.connect(self.validate)
        self.save_button.clicked.connect(self.lock_and_save)
        self.unlock_button.clicked.connect(self.unlock)
        self.automatic_button.clicked.connect(self.use_automatic)
        self.close_button.clicked.connect(self.reject)

    def _sync_canvas(self):
        self.canvas.profile = TableProfile(dict(self.profile.regions))
        self.canvas.locked = self.profile.locked
        self.canvas.labels = region_labels(self.profile.seat_layout)
        self.canvas.update()

    def _refresh_regions(self):
        previous = self.region_combo.currentData()
        self.region_combo.blockSignals(True)
        self.region_combo.clear()
        for name, label in region_labels(self.profile.seat_layout).items():
            self.region_combo.addItem(label, name)
        index = self.region_combo.findData(previous)
        self.region_combo.setCurrentIndex(max(0, index))
        self.region_combo.blockSignals(False)
        self._region_changed()
        self._render_results()

    def _region_changed(self):
        name = self.region_combo.currentData()
        self.canvas.target = name
        if name and name.startswith(('bet_', 'chips_')):
            text = '框住完整下注文字；若要確認沒有下注，請一併框選該座位上方籌碼圖示區。'
        elif name and name.startswith('back_'):
            text = '框住整個綠色牌背；沒有持牌時可留空，避免把桌布框進去。'
        elif name in ('hero', 'board'):
            text = '框住整排完整牌面。底牌必須已發兩張，才能完成底牌驗證。'
        else:
            text = '在左側拖曳框住完整文字。只需校準有問題的欄位。'
        if name and name.startswith(('bet_','stack_','back_','chips_')):
            positions={0:'自身正下方',1:'左下',2:'左側中間',3:'左上',4:'正上方',5:'右上',6:'右側中間',7:'右下'}
            seat=int(name.split('_')[1])
            text=f'座位 {seat} 位於牌桌{positions[seat]}。\n{text}'
        self.region_hint.setText(text)
        self.canvas.update()
        self._update_buttons()

    def _result_selected(self):
        row = self.results.currentRow()
        item = self.results.item(row, 0)
        if item is not None:
            index = self.region_combo.findData(item.data(Qt.ItemDataRole.UserRole))
            if index >= 0:
                self.region_combo.setCurrentIndex(index)

    def _render_results(self, readings=None, errors=None):
        readings, errors = readings or {}, errors or {}
        labels = region_labels(self.profile.seat_layout)
        self.results.setRowCount(len(self.profile.regions))
        for row, name in enumerate(self.profile.regions):
            label = QTableWidgetItem(labels.get(name, '自訂區域'))
            label.setData(Qt.ItemDataRole.UserRole, name)
            self.results.setItem(row, 0, label)
            value = errors.get(name) or readings.get(name) or ('已鎖定' if self.profile.locked else '尚未驗證')
            result = QTableWidgetItem(str(value))
            result.setToolTip(str(value))
            if name in errors:
                result.setForeground(QColor('#FFAAAA'))
            elif name in readings:
                result.setForeground(QColor('#8DDCB5'))
            self.results.setItem(row, 1, result)
        self.results.resizeRowsToContents()

    def _update_buttons(self):
        if not hasattr(self, 'save_button'):
            return
        busy = self.worker is not None or self._pending_close
        ready = self.table_combo.currentData() is not None and not self.canvas.image.isNull()
        self.validate_button.setEnabled(ready and bool(self.profile.regions) and not busy and not self.profile.locked)
        self.save_button.setEnabled(ready and self.profile.verified and not busy and not self.profile.locked)
        self.unlock_button.setEnabled(self.profile.locked and not self._pending_close)
        self.automatic_button.setEnabled(not busy)
        self.clear_region_button.setEnabled(not self.profile.locked and self.region_combo.currentData() in self.profile.regions and not self._pending_close)
        self.canvas.setEnabled(not self._pending_close)
        self.layout_combo.setEnabled(not self.profile.locked and not self._pending_close)
        self.preview_button.setEnabled(not self._pending_close)

    def _invalidate(self, message):
        self._generation += 1
        if self.worker is not None:
            self.worker.requestInterruption()
        self.profile = self.profile.unlock()
        self._sync_canvas()
        self._render_results()
        self.status.setText(message)
        self._update_buttons()

    def _canvas_selected(self, name):
        self.set_region(name, self.canvas.profile.regions[name])

    def set_region(self, name, region):
        if self.profile.locked or self.canvas.image.isNull():
            return
        self.profile = self.profile.with_region(name, region)
        self._invalidate('框選已更新，請重新驗證讀取。')

    def clear_region(self):
        name = self.region_combo.currentData()
        if self.profile.locked or name not in self.profile.regions:
            return
        regions = dict(self.profile.regions)
        regions.pop(name)
        self.profile = CalibrationProfile(regions, self.profile.reference_size, self.profile.seat_layout)
        self._invalidate('此欄位已恢復自動定位；剩餘框選需重新驗證。')

    def _layout_changed(self):
        seat_layout = self.layout_combo.currentData()
        if seat_layout == self.profile.seat_layout:
            return
        allowed = region_labels(seat_layout)
        regions = {name: region for name, region in self.profile.regions.items() if name in allowed}
        self.profile = CalibrationProfile(regions, self.profile.reference_size, seat_layout)
        self._invalidate('牌桌版型已變更，請重新確認框選並驗證。')
        self._refresh_regions()

    def refresh_tables(self):
        if self._pending_close:
            return
        previous = self.table_combo.currentData()
        try:
            tables = [table for table in self.table_provider()
                      if any(hint in table.title.casefold() for hint in ('盲注', 'blind'))]
        except Exception:
            tables = []
        desired = previous if previous is not None else self._initial_handle
        self.table_combo.blockSignals(True)
        self.table_combo.clear()
        for table in tables:
            self.table_combo.addItem(table.title, table.handle)
        index = self.table_combo.findData(desired)
        self.table_combo.setCurrentIndex(max(0, index) if tables else -1)
        self.table_combo.blockSignals(False)
        handle = self.table_combo.currentData()
        if handle != self._selected_handle:
            self._table_changed()
        elif handle is not None:
            self.refresh_preview()
        else:
            self.status.setText('等待牌桌；開啟含盲注資訊的牌桌後，按「更新預覽」。')
            self._update_buttons()
        self._tables_initialized = True

    def _table_changed(self):
        handle = self.table_combo.currentData()
        if handle == self._selected_handle:
            return
        if self._tables_initialized or self._selected_handle is not None:
            self._invalidate('牌桌已切換，請更新框選並重新驗證。')
        self._selected_handle = handle
        self.canvas.image = QImage()
        self.canvas.start = self.canvas.end = None
        self.canvas.update()
        if handle is None:
            self._preview_pending = False
            self.status.setText('等待牌桌；開啟牌桌後，按「更新預覽」。')
            self._update_buttons()
        else:
            self.refresh_preview()

    def refresh_preview(self):
        if self._pending_close or self.table_combo.currentData() is None:
            return
        if self.worker is not None:
            self._invalidate('等待上一項工作停止，再更新預覽。')
            self._preview_pending = True
            return
        self.status.setText('正在擷取所選牌桌的視窗內容…')
        self._start_worker()

    def _start_worker(self, profile=None):
        worker = _CalibrationWorker(self._generation, self.table_combo.currentData(), self.capture_factory,
                                    profile, self.validator, self.validation_timeout, self)
        self.worker = worker
        worker.preview.connect(self._accept_preview)
        worker.validated.connect(self._accept_validation)
        worker.failed.connect(self._accept_error)
        worker.finished.connect(self._worker_finished)
        self._update_buttons()
        worker.start()

    def _accept_preview(self, token, frame):
        if token != self._generation or self._pending_close:
            return
        size = (frame.shape[1], frame.shape[0])
        if size != tuple(self.profile.reference_size):
            self.profile = CalibrationProfile(dict(self.profile.regions), size, self.profile.seat_layout)
            self._invalidate('牌桌尺寸已更新，請確認框選並重新驗證。')
        elif self.profile.locked:
            self.status.setText('已載入鎖定位置；按「重新校準」才能修改。')
        else:
            self.status.setText('預覽已定格；選擇欄位並拖曳框選，再驗證讀取。')
        self.canvas.set_frame(frame)
        self._sync_canvas()
        self._update_buttons()

    def validate(self):
        if self.worker is not None or not self.profile.regions or self.profile.locked or self.canvas.image.isNull():
            return
        self._invalidate('正在取得三個新影格並逐欄驗證…')
        self._start_worker(self.profile)

    def _accept_validation(self, token, value):
        if token != self._generation or self._pending_close:
            return
        if value.signature != self.profile.signature:
            self.status.setText('校準區域與本次結果不一致，請重新驗證讀取。')
            return
        self._render_results(value.readings, value.errors)
        if value.valid:
            self.profile = self.profile.mark_verified()
            self.status.setText('所選欄位讀取通過，可以鎖定並儲存。無下注確認需一併框選籌碼區。')
        else:
            self.status.setText('驗證未通過；請按表格選擇問題欄位、重新框選，再重試。')
        self._update_buttons()

    def _accept_error(self, token, message):
        if token != self._generation or self._pending_close:
            return
        self.status.setText(f'未完成：{message}')
        self._render_results(errors={name: message for name in self.profile.regions})
        self._update_buttons()

    def _worker_finished(self):
        worker = self.sender()
        if self.worker is worker:
            self.worker = None
        worker.deleteLater()
        if self._pending_close:
            QDialog.done(self, self._closing_result)
        elif self._preview_pending:
            self._preview_pending = False
            self.refresh_preview()
        else:
            self._update_buttons()

    def lock_and_save(self):
        if self.worker is not None or self.canvas.image.isNull() or self.table_combo.currentData() is None:
            return
        try:
            profile = self.profile.lock()
            self.store.save(profile)
            self.profile = profile
            self._sync_canvas()
            self.on_saved()
            self.status.setText('位置已鎖定並儲存，已通知目前辨識流程套用。')
        except (ValueError, OSError) as error:
            self.status.setText(f'未儲存：{error}')
        self._update_buttons()

    def unlock(self):
        self._invalidate('已解鎖；重新框選後必須再次驗證並儲存。')

    def use_automatic(self):
        if self.worker is not None:
            return
        try:
            profile = CalibrationProfile({}, self.profile.reference_size, self.profile.seat_layout)
            self.store.save(profile)
            self.profile = profile
            self._invalidate('已儲存自動定位設定；目前辨識流程將重新定位。')
            self.on_saved()
        except (ValueError, OSError) as error:
            self.status.setText(f'未儲存：{error}')
        self._update_buttons()

    def _request_close(self, result):
        self._closing_result = result
        self._pending_close = True
        self._preview_pending = False
        self._generation += 1
        self.worker.requestInterruption()
        self.status.setText('正在停止背景工作，完成後會自動關閉…')
        self._update_buttons()

    def done(self, result):
        if self.worker is not None:
            self._request_close(result)
            return
        self._pending_close = True
        self._generation += 1
        super().done(result)

    def closeEvent(self, event):
        if self.worker is not None:
            self._request_close(QDialog.DialogCode.Rejected)
            event.ignore()
        else:
            self._pending_close = True
            self._generation += 1
            super().closeEvent(event)
