import importlib.util
import json
import re
import subprocess
import sys
from dataclasses import replace

import pytest

from capture.profiles import Region


def test_修改區域必須解除鎖定並清除驗證():
    assert importlib.util.find_spec('capture.calibration') is not None, '缺少辨識位置校準模組'
    from capture.calibration import CalibrationProfile

    original = CalibrationProfile({'pot': Region(.4, .3, .2, .1)}, (1128, 799))
    locked = original.mark_verified().lock()
    changed = locked.with_region('pot', Region(.1, .2, .2, .1))
    assert locked.locked and locked.verified
    assert not changed.locked and not changed.verified
    assert changed.verified_signature == ''
    assert changed.regions['pot'] == Region(.1, .2, .2, .1)
    assert locked.regions['pot'] == original.regions['pot']


def test_驗證簽章不受字典順序影響並涵蓋尺寸與版型():
    from capture.calibration import CalibrationProfile

    regions = {'hero': Region(.4, .6, .2, .2), 'pot': Region(.4, .3, .2, .1)}
    profile = CalibrationProfile(regions, (1128, 799))
    reversed_profile = CalibrationProfile(dict(reversed(list(regions.items()))), (1128, 799))
    assert profile.signature == reversed_profile.signature
    assert isinstance(profile.signature, str) and profile.signature
    assert replace(profile, reference_size=(1146, 772)).signature != profile.signature
    assert replace(profile, seat_layout=6).signature != profile.signature


def test_區域輸入修改不影響原設定且直接修改使舊簽章失效():
    from capture.calibration import CalibrationProfile

    regions = {'pot': Region(.4, .3, .2, .1)}
    profile = CalibrationProfile(regions, (1128, 799)).mark_verified()
    regions['pot'] = Region(.1, .2, .2, .1)
    assert profile.verified
    profile.regions['pot'] = regions['pot']
    assert not profile.verified
    with pytest.raises(ValueError, match='驗證'):
        profile.lock()


def test_解鎖必須重新驗證():
    from capture.calibration import CalibrationProfile

    profile = CalibrationProfile({'pot': Region(.4, .3, .2, .1)}, (1128, 799)).mark_verified().lock()
    unlocked = profile.unlock()
    assert not unlocked.locked and not unlocked.verified
    assert unlocked.verified_signature == ''
    with pytest.raises(ValueError, match='驗證'):
        unlocked.lock()


@pytest.mark.parametrize('verified_signature', ['', '過期簽章'])
def test_未驗證不可鎖定(verified_signature):
    from capture.calibration import CalibrationProfile

    profile = CalibrationProfile({'pot': Region(.4, .3, .2, .1)}, (1128, 799), verified_signature=verified_signature)
    with pytest.raises(ValueError, match='驗證'):
        profile.lock()
    with pytest.raises(ValueError, match='驗證'):
        replace(profile, locked=True)


def test_空設定不可驗證或鎖定():
    from capture.calibration import CalibrationProfile

    profile = CalibrationProfile({}, (1128, 799))
    with pytest.raises(ValueError, match='區域'):
        profile.mark_verified()
    with pytest.raises(ValueError, match='區域'):
        profile.lock()


def test_等比例縮放與百分之三內差異可套用():
    from capture.calibration import CalibrationProfile

    profile = CalibrationProfile({'pot': Region(.4, .3, .2, .1)}, (1000, 800))
    profile.assert_compatible((2000, 1600))
    profile.assert_compatible((1029, 800))
    profile.assert_compatible((1030, 800))
    with pytest.raises(ValueError, match='比例.*重新校準'):
        profile.assert_compatible((1031, 800))
    with pytest.raises(ValueError, match='比例.*重新校準'):
        profile.assert_compatible((1000, 1200))
    with pytest.raises(ValueError, match='比例.*重新校準'):
        profile.assert_compatible((10 ** 400, 800))


@pytest.mark.parametrize('size', [(0, 800), (1000, -1), (True, 800), (1000.0, 800), (1000,), '畫面'])
def test_拒絕無效畫面尺寸(size):
    from capture.calibration import CalibrationProfile

    profile = CalibrationProfile({'pot': Region(.4, .3, .2, .1)}, (1000, 800))
    with pytest.raises(ValueError, match='尺寸'):
        profile.assert_compatible(size)


@pytest.mark.parametrize('change', [
    {'regions': []}, {'regions': {'未知': Region(.1, .1, .2, .2)}},
    {'regions': {'pot': (.1, .1, .2, .2)}},
    {'regions': {'pot': Region(False, .1, .2, .2)}},
    {'reference_size': (True, 800)}, {'reference_size': (1000.0, 800)},
    {'reference_size': (0, 800)}, {'reference_size': (1000,)},
    {'seat_layout': True}, {'seat_layout': '8'}, {'seat_layout': 7},
    {'locked': 1}, {'verified_signature': None},
    {'regions': {'stack_0': Region(.1, .1, .2, .2)}},
    {'regions': {'back_0': Region(.1, .1, .2, .2)}},
    {'regions': {'bet_2': Region(.1, .1, .2, .2)}, 'seat_layout': 6},
])
def test_拒絕無效校準欄位(change):
    from capture.calibration import CalibrationProfile

    values = {'regions': {'pot': Region(.4, .3, .2, .1)}, 'reference_size': (1128, 799)}
    values.update(change)
    with pytest.raises(ValueError) as error:
        CalibrationProfile(**values)
    assert re.search('[\u4e00-\u9fff]', str(error.value))


@pytest.mark.parametrize('layout,seats', [(6, {0, 1, 3, 4, 5, 7}), (8, set(range(8)))])
def test_預設區域包含實際座位與中文標籤(layout, seats):
    from capture.calibration import default_regions, region_labels
    from vision.card_detector import HERO_REGION, BOARD_REGION
    from vision.player_detector import SEAT_REGIONS, SIX_SEAT_REGIONS
    from vision.table_detector import BET_ROIS, SIX_BET_ROIS, POT_ROI

    regions = default_regions(layout)
    labels = region_labels(layout)
    assert set(regions) == set(labels)
    assert set(seats) == {int(name.split('_')[1]) for name in regions if name.startswith('bet_')}
    assert regions['hero'] == Region(*HERO_REGION)
    assert regions['board'] == Region(*BOARD_REGION)
    assert regions['pot'] == Region(*POT_ROI)
    expected_bets = SIX_BET_ROIS if layout == 6 else BET_ROIS
    expected_backs = SIX_SEAT_REGIONS if layout == 6 else SEAT_REGIONS
    for seat in seats:
        assert regions[f'bet_{seat}'] == Region(*expected_bets[seat])
        assert f'chips_{seat}' in regions
        if seat:
            assert regions[f'back_{seat}'] == Region(*expected_backs[seat])
            assert f'stack_{seat}' in regions
    assert 'stack_0' not in regions and 'back_0' not in regions
    assert all(isinstance(region, Region) for region in regions.values())
    assert all(re.search('[\u4e00-\u9fff]', label) for label in labels.values())
    regions.pop('pot')
    assert 'pot' in default_regions(layout)


@pytest.mark.parametrize('layout', [True, '6', 7])
def test_標籤與預設拒絕未知版型(layout):
    from capture.calibration import default_regions, region_labels

    for function in (default_regions, region_labels):
        with pytest.raises(ValueError, match='座位'):
            function(layout)


def test_只載入設定模組不提早載入辨識器():
    script = "import sys\nimport capture.calibration\nassert 'vision.table_detector' not in sys.modules\nassert 'vision.card_detector' not in sys.modules\n"
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('locked', [False, True])
def test_設定原子儲存後可還原單區覆寫(tmp_path, locked):
    from capture.calibration import CalibrationProfile, CalibrationStore, default_regions

    path = tmp_path / '設定' / '辨識位置.json'
    store = CalibrationStore(path)
    assert store.load() is None
    profile = CalibrationProfile({'pot': Region(.1, .2, .2, .1)}, (1128, 799), seat_layout=6)
    if locked:
        profile = profile.mark_verified().lock()
    store.save(profile)
    restored = store.load()
    assert restored == profile
    assert restored.locked is locked
    assert set(restored.regions) == {'pot'}
    combined = {**default_regions(6), **restored.regions}
    assert combined['pot'] == profile.regions['pot']
    assert combined['hero'] == default_regions(6)['hero']
    assert list(path.parent.iterdir()) == [path]


def test_毀損檔案錯誤必須是中文(tmp_path):
    from capture.calibration import CalibrationStore

    path = tmp_path / '辨識位置.json'
    for content in ('{', '[]', 'null'):
        path.write_text(content, encoding='utf-8')
        with pytest.raises(ValueError, match='設定'):
            CalibrationStore(path).load()
    path.write_bytes(b'\xff\xfe\xff')
    with pytest.raises(ValueError, match='設定'):
        CalibrationStore(path).load()


@pytest.mark.parametrize('change', [
    {'schema_version': 2}, {'schema_version': True},
    {'regions': []}, {'reference_size': [0, 799]}, {'reference_size': [1128.5, 799]},
    {'reference_size': [True, 799]}, {'reference_size': [1128]},
    {'seat_layout': 7}, {'seat_layout': True}, {'seat_layout': '8'},
    {'locked': 'false'}, {'verified_signature': 23},
    {'locked': True, 'verified_signature': ''},
    {'regions': {'unknown': {'x': .1, 'y': .1, 'width': .2, 'height': .2}}},
    {'regions': {'stack_0': {'x': .1, 'y': .1, 'width': .2, 'height': .2}}},
    {'regions': {'bet_2': {'x': .1, 'y': .1, 'width': .2, 'height': .2}}, 'seat_layout': 6},
    {'regions': {'pot': [.1, .1, .2, .2]}},
    {'regions': {'pot': {'x': '0.1', 'y': .1, 'width': .2, 'height': .2}}},
    {'regions': {'pot': {'x': False, 'y': .1, 'width': .2, 'height': .2}}},
    {'regions': {'pot': {'x': float('nan'), 'y': .1, 'width': .2, 'height': .2}}},
    {'regions': {'pot': {'x': 10 ** 400, 'y': .1, 'width': .2, 'height': .2}}},
    {'regions': {'pot': {'x': -.1, 'y': .1, 'width': .2, 'height': .2}}},
    {'regions': {'pot': {'x': .9, 'y': .1, 'width': .2, 'height': .2}}},
    {'regions': {'pot': {'x': .1, 'y': .1, 'width': 0, 'height': .2}}},
    {'regions': {'pot': {'x': .1, 'y': .1, 'width': .2}}},
    {'regions': {'pot': {'x': .1, 'y': .1, 'width': .2, 'height': .2, 'extra': 1}}},
])
def test_讀取拒絕無效格式欄位與座標(tmp_path, change):
    from capture.calibration import CalibrationProfile, CalibrationStore

    path = tmp_path / '辨識位置.json'
    store = CalibrationStore(path)
    store.save(CalibrationProfile({'pot': Region(.4, .3, .2, .1)}, (1128, 799)))
    data = json.loads(path.read_text(encoding='utf-8'))
    data.update(change)
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError) as error:
        store.load()
    assert re.search('[\u4e00-\u9fff]', str(error.value))


def test_修改鎖定檔案座標不可沿用舊驗證(tmp_path):
    from capture.calibration import CalibrationProfile, CalibrationStore

    path = tmp_path / '辨識位置.json'
    store = CalibrationStore(path)
    store.save(CalibrationProfile({'pot': Region(.4, .3, .2, .1)}, (1128, 799)).mark_verified().lock())
    data = json.loads(path.read_text(encoding='utf-8'))
    data['regions']['pot']['x'] = .1
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='驗證'):
        store.load()


def test_原子取代失敗保留原檔且清除暫存檔(tmp_path, monkeypatch):
    from capture.calibration import CalibrationProfile, CalibrationStore
    import capture.calibration as calibration

    path = tmp_path / '辨識位置.json'
    store = CalibrationStore(path)
    original = CalibrationProfile({'pot': Region(.4, .3, .2, .1)}, (1128, 799))
    store.save(original)
    saved = path.read_bytes()

    def refuse_replace(source, target):
        assert source.parent == target.parent
        assert json.loads(source.read_text(encoding='utf-8'))['regions']['pot']['x'] == .1
        assert target.read_bytes() == saved
        raise OSError('測試取代失敗')

    monkeypatch.setattr(calibration.os, 'replace', refuse_replace)
    with pytest.raises(OSError, match='儲存'):
        store.save(original.with_region('pot', Region(.1, .2, .2, .1)))
    assert path.read_bytes() == saved
    assert store.load() == original
    assert list(tmp_path.iterdir()) == [path]


def test_自動定位的空設定可保存並覆寫舊校準(tmp_path):
    from capture.calibration import CalibrationProfile, CalibrationStore

    path = tmp_path / '辨識位置.json'
    store = CalibrationStore(path)
    store.save(CalibrationProfile({'pot': Region(.4, .3, .2, .1)}, (1128, 799)).mark_verified().lock())
    automatic = CalibrationProfile({}, (1128, 799))
    store.save(automatic)
    assert store.load() == automatic


def test_不保存被外部修改而失效的鎖定設定(tmp_path):
    from capture.calibration import CalibrationProfile, CalibrationStore

    path = tmp_path / '辨識位置.json'
    store = CalibrationStore(path)
    profile = CalibrationProfile({'pot': Region(.4, .3, .2, .1)}, (1128, 799)).mark_verified().lock()
    store.save(profile)
    saved = path.read_bytes()
    profile.regions['pot'] = Region(.1, .2, .2, .1)
    with pytest.raises(ValueError, match='驗證'):
        store.save(profile)
    assert path.read_bytes() == saved
