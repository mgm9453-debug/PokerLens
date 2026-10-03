import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_region_tracks_position_and_size():
    from capture.window_capture import region_rect
    assert region_rect((100, 200, 1100, 700), (.4, .68, .22, .2)) == (500, 540, 720, 640)
    assert region_rect((-100, 0, 400, 250), (.4, .68, .22, .2)) == (100, 170, 210, 220)


def test_region_rejects_bad_size():
    from capture.window_capture import region_rect
    with pytest.raises(ValueError):
        region_rect((0, 0, 0, 100), (.4, .68, .22, .2))


def test_occlusion_requires_positive_intersection():
    from capture.window_capture import regions_occluded
    table = (100, 200, 1100, 700)
    regions = [(.4, .68, .22, .2)]
    assert regions_occluded(table, regions, [(600, 600, 800, 800)])
    assert not regions_occluded(table, regions, [(720, 540, 800, 640)])
    assert not regions_occluded(table, regions, [(0, 0, 200, 200)])


def test_read_tracks_current_rectangle_and_converts_bgr(monkeypatch):
    import numpy as np
    from capture import window_capture as module
    class Source:
        def grab(self, rect):
            assert rect == {'left': 10, 'top': 20, 'width': 3, 'height': 2}
            return np.full((2, 3, 4), [1, 2, 3, 255], dtype=np.uint8)
    monkeypatch.setattr(module, '_validated_rect', lambda handle, regions: (10, 20, 13, 22))
    capture = module.WindowCapture(123)
    capture._source = Source()
    assert capture.read().tolist() == [[[1, 2, 3]] * 3] * 2


def test_read_requires_open():
    from capture.window_capture import WindowCapture
    with pytest.raises(RuntimeError, match='尚未開啟'):
        WindowCapture(123).read()


def test_read_rejects_move_during_capture(monkeypatch):
    import numpy as np
    from capture import window_capture as module
    rects = iter([(0, 0, 3, 2), (1, 0, 4, 2)])
    monkeypatch.setattr(module, '_validated_rect', lambda handle, regions: next(rects))
    class Source:
        def grab(self, rect):
            return np.zeros((2, 3, 4), dtype=np.uint8)
    capture = module.WindowCapture(123)
    capture._source = Source()
    with pytest.raises(RuntimeError, match='位置正在變動'):
        capture.read()


def test_open_refuses_obstructed_table_before_capture(monkeypatch):
    from capture import window_capture as module
    def refuse(handle, regions):
        raise RuntimeError('底牌或公共牌被其他視窗遮住')
    monkeypatch.setattr(module, '_validated_rect', refuse)
    with pytest.raises(RuntimeError, match='遮住'):
        module.WindowCapture(123).open()
