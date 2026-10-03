import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_latest_frame_replaces_old():
    from capture.frame_buffer import FrameBuffer
    buffer = FrameBuffer()
    buffer.put('前一幀')
    buffer.put('最新幀')
    assert buffer.get() == '最新幀'
    assert buffer.get() is None


def test_roi_round_trip(tmp_path):
    from capture.profiles import TableProfile, Region
    profile = TableProfile({'底牌': Region(0.1, 0.2, 0.3, 0.4)})
    path = tmp_path / '區域.json'
    profile.save(path)
    assert TableProfile.load(path).regions == profile.regions


def test_roi_rejects_outside():
    import pytest
    from capture.profiles import Region
    with pytest.raises(ValueError):
        Region(0.8, 0, 0.4, 0.2)
