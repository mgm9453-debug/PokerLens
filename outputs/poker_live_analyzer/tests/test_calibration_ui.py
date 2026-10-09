"""用假牌桌來源驗證校準操作，不存取真實遊戲或使用者資料。"""
import asyncio
import importlib
import os
import threading
from time import monotonic
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def ui_module():
    try:
        return importlib.import_module('ui.calibration_dialog')
    except ModuleNotFoundError as error:
        if error.name == 'ui.calibration_dialog':
            pytest.fail('尚未提供可操作的手動校準視窗')
        raise


def wait_until(predicate, timeout=3000):
    deadline = monotonic() + timeout / 1000
    while not predicate() and monotonic() < deadline:
        QTest.qWait(10)
    assert predicate(), '背景操作未在期限內完成'


def table(handle=11, title='盲注 10 / 20'):
    return SimpleNamespace(handle=handle, title=title, rect=(0, 0, 1000, 500))


class FakeSources:
    def __init__(self, *, frozen=False, gate=None):
        self.calls = []
        self.closed = []
        self.frozen = frozen
        self.gate = gate

    def __call__(self, handle):
        owner = self

        class Source:
            _received = 1.0

            def open(self):
                pass

            def read(self):
                owner.calls.append(handle)
                if owner.gate is not None:
                    owner.gate.wait(2)
                if not owner.frozen:
                    self._received += 1
                return np.full((500, 1000, 3), 32 + len(owner.calls) % 100, np.uint8)

            def close(self):
                owner.closed.append(handle)

        return Source()


async def valid_readings(profile, frames):
    assert len(frames) >= 3
    return SimpleNamespace(valid=True, readings={name: '讀到 123' for name in profile.regions},
                           errors={}, signature=profile.signature)


def dialog(tmp_path, **kwargs):
    module = ui_module()
    kwargs.setdefault('table_provider', lambda: [table()])
    kwargs.setdefault('capture_factory', FakeSources())
    kwargs.setdefault('validator', valid_readings)
    result = module.CalibrationDialog(tmp_path / 'recognition.json', kwargs.pop('on_saved', lambda: None), **kwargs)
    result.show()
    return result


def ready(result):
    wait_until(lambda: not result.canvas.image.isNull() and result.worker is None)


def set_pot(result):
    from capture.profiles import Region
    result.set_region('pot', Region(.3, .2, .2, .1))


def test_no_open_table_waits_and_cannot_verify(app, tmp_path):
    result = dialog(tmp_path, table_provider=lambda: [])
    QTest.qWait(20)
    assert '等待牌桌' in result.status.text()
    assert not result.validate_button.isEnabled()
    assert not result.save_button.isEnabled()
    result.close()


def test_only_playing_tables_are_offered_and_initial_handle_is_used(app, tmp_path):
    sources = FakeSources()
    result = dialog(tmp_path, capture_factory=sources, initial_handle=22,
                    table_provider=lambda: [table(1, '遊戲大廳'), table(), table(22, 'Blinds 20 / 40')])
    ready(result)
    assert result.table_combo.count() == 2
    assert result.table_combo.currentData() == 22
    assert result.selected_handle == 22
    assert sources.calls == [22]
    QTest.qWait(80)
    assert sources.calls == [22], '預覽必須定格，避免拖曳時換幀'
    assert sources.closed == [22]
    result.close()


def test_seat_hint_identifies_position_when_selecting_bet_field(app,tmp_path):
    result=dialog(tmp_path)
    ready(result)
    result.region_combo.setCurrentIndex(result.region_combo.findData('bet_3'))
    assert '左上' in result.region_hint.text()
    assert '籌碼' in result.region_hint.text()
    result.region_combo.setCurrentIndex(result.region_combo.findData('back_7'))
    assert '右下' in result.region_hint.text()
    assert '綠色' in result.region_hint.text()
    result.close()


def test_drag_uses_displayed_image_rect_and_locked_canvas_does_not_edit(app):
    canvas = ui_module().CalibrationCanvas()
    canvas.set_frame(np.zeros((500, 1000, 3), np.uint8))
    canvas.resize(900, 650)
    canvas.target = 'pot'
    canvas.show()
    rect = canvas.image_rect()
    start = QPoint(round(rect.x() + .1 * rect.width()), round(rect.y() + .2 * rect.height()))
    end = QPoint(round(rect.x() + .4 * rect.width()), round(rect.y() + .6 * rect.height()))
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas, end)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
    region = canvas.profile.regions['pot']
    assert (region.x, region.y, region.width, region.height) == pytest.approx((.1, .2, .3, .4), abs=.003)
    canvas.locked = True
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=end)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=start)
    assert canvas.profile.regions['pot'] == region
    canvas.close()


def test_validation_reads_fresh_frames_and_saves_only_overrides(app, tmp_path):
    from capture.calibration import CalibrationStore
    saved = []
    sources = FakeSources()
    result = dialog(tmp_path, capture_factory=sources, on_saved=lambda: saved.append(True))
    ready(result)
    set_pot(result)
    result.validate_button.click()
    wait_until(lambda: result.worker is None)
    assert result.profile.verified
    assert result.save_button.isEnabled()
    assert len(sources.calls) == 4
    assert '讀到 123' in result.results.item(0, 1).text()
    result.save_button.click()
    profile = CalibrationStore(tmp_path / 'recognition.json').load()
    assert profile.locked
    assert set(profile.regions) == {'pot'}
    assert saved == [True]
    assert result.canvas.locked
    result.unlock_button.click()
    assert not result.profile.verified and not result.canvas.locked
    result.close()


def test_failed_field_prevents_lock_and_keeps_retry_available(app, tmp_path):
    async def invalid(profile, frames):
        return SimpleNamespace(valid=False, readings={}, errors={'pot': '未讀到金額'}, signature=profile.signature)
    result = dialog(tmp_path, validator=invalid)
    ready(result)
    set_pot(result)
    result.validate_button.click()
    wait_until(lambda: result.worker is None)
    assert not result.save_button.isEnabled()
    assert result.validate_button.isEnabled()
    assert '未讀到金額' in result.results.item(0, 1).text()
    assert not (tmp_path / 'recognition.json').exists()
    result.close()


def test_edit_while_validation_runs_discards_older_success(app, tmp_path):
    from capture.profiles import Region
    entered = threading.Event()
    release = threading.Event()
    async def delayed(profile, frames):
        entered.set()
        while not release.is_set():
            await asyncio.sleep(.01)
        return await valid_readings(profile, frames)
    result = dialog(tmp_path, validator=delayed)
    ready(result)
    set_pot(result)
    result.validate_button.click()
    wait_until(entered.is_set)
    result.set_region('pot', Region(.5, .2, .2, .1))
    release.set()
    wait_until(lambda: result.worker is None)
    assert not result.profile.verified
    assert not result.save_button.isEnabled()
    assert '讀到 123' not in result.results.item(0, 1).text()
    result.close()


def test_layout_change_clears_verified_geometry_and_limits_seats(app, tmp_path):
    result = dialog(tmp_path)
    ready(result)
    set_pot(result)
    result.validate_button.click()
    wait_until(lambda: result.worker is None)
    result.layout_combo.setCurrentIndex(result.layout_combo.findData(6))
    assert result.profile.seat_layout == 6
    assert not result.profile.verified
    names = {result.region_combo.itemData(i) for i in range(result.region_combo.count())}
    assert 'bet_2' not in names and 'bet_6' not in names
    assert 'chips_7' in names
    result.close()


def test_same_cached_frame_cannot_count_as_three_new_frames(app, tmp_path):
    called = []
    async def validator(profile, frames):
        called.append(True)
        return await valid_readings(profile, frames)
    result = dialog(tmp_path, capture_factory=FakeSources(frozen=True), validator=validator, validation_timeout=.15)
    ready(result)
    set_pot(result)
    result.validate_button.click()
    wait_until(lambda: result.worker is None)
    assert called == []
    assert not result.profile.verified
    assert '新影格' in result.status.text()
    result.close()


def test_close_is_nonblocking_and_waits_for_running_capture_to_finish(app, tmp_path):
    gate = threading.Event()
    sources = FakeSources(gate=gate)
    result = dialog(tmp_path, capture_factory=sources)
    wait_until(lambda: bool(sources.calls))
    worker = result.worker
    started = monotonic()
    result.close()
    assert monotonic() - started < .15
    assert worker.isInterruptionRequested()
    assert result.isVisible(), '執行緒結束前不可銷毀視窗'
    gate.set()
    wait_until(lambda: not result.isVisible() and result.worker is None)
    assert sources.closed == [11]


def test_saved_locked_profile_prefills_and_automatic_choice_persists(app, tmp_path):
    from capture.calibration import CalibrationProfile, CalibrationStore
    from capture.profiles import Region
    store = CalibrationStore(tmp_path / 'recognition.json')
    store.save(CalibrationProfile({'pot': Region(.3, .2, .2, .1)}, (1000, 500)).mark_verified().lock())
    saved = []
    result = dialog(tmp_path, on_saved=lambda: saved.append(True))
    ready(result)
    assert result.profile.locked and result.canvas.locked
    assert result.canvas.profile.regions['pot'] == Region(.3, .2, .2, .1)
    assert not result.validate_button.isEnabled()
    result.automatic_button.click()
    assert store.load().regions == {}
    assert not store.load().locked
    assert saved == [True]
    result.close()


def test_table_switch_during_validation_discards_result_and_captures_selected_table(app, tmp_path):
    entered = threading.Event()
    release = threading.Event()
    async def delayed(profile, frames):
        entered.set()
        while not release.is_set():
            await asyncio.sleep(.01)
        return await valid_readings(profile, frames)
    sources = FakeSources()
    result = dialog(tmp_path, validator=delayed, capture_factory=sources,
                    table_provider=lambda: [table(), table(22)])
    ready(result)
    set_pot(result)
    result.validate_button.click()
    wait_until(entered.is_set)
    result.table_combo.setCurrentIndex(result.table_combo.findData(22))
    release.set()
    ready(result)
    assert sources.calls[-1] == 22
    assert not result.profile.verified
    assert not result.save_button.isEnabled()
    result.close()


def test_refreshed_preview_size_clears_previous_verification(app, tmp_path):
    sources = FakeSources()
    result = dialog(tmp_path, capture_factory=sources)
    ready(result)
    set_pot(result)
    result.validate_button.click()
    wait_until(lambda: result.worker is None)
    assert result.profile.verified
    class ResizedSource:
        def open(self):
            pass
        def read(self):
            return np.full((600, 1000, 3), 32, np.uint8)
        def close(self):
            pass
    result.capture_factory = lambda handle: ResizedSource()
    result.preview_button.click()
    ready(result)
    assert result.profile.reference_size == (1000, 600)
    assert not result.profile.verified
    assert not result.save_button.isEnabled()
    result.close()


def test_service_signature_mismatch_never_enables_save(app, tmp_path):
    async def wrong_signature(profile, frames):
        return SimpleNamespace(valid=True, readings={'pot': '讀到 123'}, errors={}, signature='過期幾何')
    result = dialog(tmp_path, validator=wrong_signature)
    ready(result)
    set_pot(result)
    result.validate_button.click()
    wait_until(lambda: result.worker is None)
    assert not result.profile.verified
    assert not result.save_button.isEnabled()
    assert '重新驗證' in result.status.text()
    result.close()


def test_close_button_also_waits_for_capture_shutdown(app, tmp_path):
    gate = threading.Event()
    sources = FakeSources(gate=gate)
    result = dialog(tmp_path, capture_factory=sources)
    wait_until(lambda: bool(sources.calls))
    worker = result.worker
    result.close_button.click()
    assert worker.isInterruptionRequested()
    assert result.isVisible()
    gate.set()
    wait_until(lambda: not result.isVisible() and result.worker is None)


def test_capture_error_is_chinese_and_preview_can_retry(app, tmp_path):
    class BrokenSource:
        def open(self):
            raise RuntimeError('native failure')
        def close(self):
            pass
    result = dialog(tmp_path, capture_factory=lambda handle: BrokenSource())
    wait_until(lambda: '未完成' in result.status.text() and result.worker is None)
    assert '重試' in result.status.text()
    assert 'native failure' not in result.status.text()
    result.capture_factory = FakeSources()
    result.preview_button.click()
    ready(result)
    result.close()


def test_close_before_initial_preview_does_not_start_a_capture(app, tmp_path):
    sources = FakeSources()
    result = ui_module().CalibrationDialog(tmp_path / 'recognition.json', lambda: None,
        table_provider=lambda: [table()], capture_factory=sources, validator=valid_readings)
    result.close()
    QTest.qWait(50)
    assert result.worker is None
    assert sources.calls == []
