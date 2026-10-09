"""即時工作執行緒每幀確認固定區域與畫面比例。"""
import json
from types import SimpleNamespace
import numpy as np
import pytest
from capture.profiles import Region
from vision.card_detector import Detection
from vision.player_detector import PlayerDetection
from vision.table_detector import TableAmounts
import vision.worker as module


def config():
    from capture.calibration import CalibrationProfile
    return CalibrationProfile({'call_amount': Region(.1, .1, .1, .1)}, (1128, 799)).mark_verified().lock()


def run_frames(monkeypatch, tmp_path, images, missing_call=False, mutate_on_read=False):
    profile = config()
    calls = []
    counter = {'read': 0}
    class Capture:
        def __init__(self, *args, **kwargs):
            pass
        def open(self):
            pass
        def read(self):
            image = images[counter['read']]
            counter['read'] += 1
            if mutate_on_read:
                profile.regions['call_amount'] = Region(.2, .2, .1, .1)
            return image
        def close(self):
            pass
    class Cards:
        def detect(self, image):
            calls.append(image.shape[:2])
            return Detection((), (), 1, True, hero_reliable=True, hero_confidence=1, board_reliable=True)
    class Players:
        seat_layout = 8
        def detect(self, image):
            return PlayerDetection((), True)
    class Money:
        ocr = SimpleNamespace(big_blind=None)
        def set_seat_layout(self, layout):
            pass
        async def detect(self, image):
            return TableAmounts(125, 1000, None if missing_call else 0, {seat: 0 for seat in range(8)},
                not missing_call, '缺少必要金額' if missing_call else '', 0,
                field_reliable={'pot': True, 'hero_stack': True, 'call_amount': not missing_call})
        def reset(self):
            pass
    def build(received=None, **kwargs):
        assert received is profile
        return Cards(), Players(), Money()
    monkeypatch.setattr(module, 'WindowCapture', Capture)
    monkeypatch.setattr(module, 'build_detectors', build)
    monkeypatch.setattr('capture.window_capture.list_tables', lambda: [])
    worker = module.VisionWorker(1, calibration=profile, diagnostic_path=tmp_path / '辨識.json')
    worker.refresh_ms = 0
    monkeypatch.setattr(worker, 'isInterruptionRequested', lambda: counter['read'] >= len(images))
    unavailable, statuses = [], []
    worker.unavailable.connect(unavailable.append)
    worker.status.connect(statuses.append)
    worker.run()
    report = json.loads((tmp_path / '辨識.json').read_text(encoding='utf-8'))
    return calls, unavailable, statuses, report, profile


def test_worker_refuses_changed_ratio_before_detector_reads(monkeypatch, tmp_path):
    images = [np.full((799, 1128, 3), 90, np.uint8), np.full((799, 900, 3), 90, np.uint8)]
    calls, unavailable, statuses, report, profile = run_frames(monkeypatch, tmp_path, images)
    assert calls == [(799, 1128)]
    assert unavailable and '比例' in unavailable[-1]
    assert report['calibration']['signature'] == profile.signature
    assert report['calibration']['compatible'] is False
    assert report['frame_size'] == [799, 900]


def test_worker_reports_exact_failed_calibration_field(monkeypatch, tmp_path):
    images = [np.full((799, 1128, 3), 90, np.uint8)]
    calls, unavailable, statuses, report, profile = run_frames(monkeypatch, tmp_path, images, missing_call=True)
    assert any('請校準跟注金額區域' in text for text in statuses)
    assert report['calibration']['active'] is True
    assert report['calibration']['reference_size'] == [1128, 799]


@pytest.mark.parametrize('failure', ['capture', 'detectors', 'event_loop'])
def test_worker_initialization_failure_reports_and_closes_resources(monkeypatch, tmp_path, failure):
    closed = []
    created = []
    def fail():
        raise RuntimeError('初始化失敗，請重新校準')
    class Capture:
        def __init__(self, *args, **kwargs):
            if failure == 'capture':
                fail()
            created.append('capture')
        def close(self):
            closed.append('capture')
    class Loop:
        def close(self):
            closed.append('event_loop')
    def detectors(*args, **kwargs):
        if failure == 'detectors':
            fail()
        return SimpleNamespace(), SimpleNamespace(), SimpleNamespace()
    def event_loop():
        if failure == 'event_loop':
            fail()
        created.append('event_loop')
        return Loop()
    monkeypatch.setattr(module, 'WindowCapture', Capture)
    monkeypatch.setattr(module, 'build_detectors', detectors)
    monkeypatch.setattr(module.asyncio, 'new_event_loop', event_loop)
    worker = module.VisionWorker(1, calibration=config(), diagnostic_path=tmp_path / '啟動失敗.json')
    monkeypatch.setattr(worker, 'isInterruptionRequested', lambda: True)
    unavailable, statuses, equity = [], [], []
    worker.unavailable.connect(unavailable.append)
    worker.status.connect(statuses.append)
    worker.equity_view.connect(equity.append)
    worker.run()
    assert unavailable == statuses == ['初始化失敗，請重新校準']
    assert equity == [None]
    assert sorted(closed) == sorted(created)
    report = json.loads((tmp_path / '啟動失敗.json').read_text(encoding='utf-8'))
    assert report['frame_size'] is None
    assert report['message'] == '初始化失敗，請重新校準'


def test_worker_refuses_signature_mutation_before_any_frame_detection(monkeypatch, tmp_path):
    image = np.full((799, 1128, 3), 90, np.uint8)
    calls, unavailable, statuses, report, profile = run_frames(monkeypatch, tmp_path, [image], mutate_on_read=True)
    assert calls == []
    assert unavailable and statuses and '校準' in unavailable[-1]
    assert report['calibration']['active'] is False
    assert report['calibration']['verified'] is False


def test_worker_startup_refuses_invalid_locked_signature(monkeypatch, tmp_path):
    profile = config()
    profile.regions['call_amount'] = Region(.2, .2, .1, .1)
    closed = []
    class Capture:
        def __init__(self, *args, **kwargs):
            pass
        def close(self):
            closed.append(True)
    monkeypatch.setattr(module, 'WindowCapture', Capture)
    worker = module.VisionWorker(1, calibration=profile, diagnostic_path=tmp_path / '簽章失效.json')
    monkeypatch.setattr(worker, 'isInterruptionRequested', lambda: True)
    unavailable, statuses = [], []
    worker.unavailable.connect(unavailable.append)
    worker.status.connect(statuses.append)
    worker.run()
    assert unavailable and statuses and '校準' in unavailable[-1]
    assert closed == [True]
    report = json.loads((tmp_path / '簽章失效.json').read_text(encoding='utf-8'))
    assert report['calibration']['verified'] is False
