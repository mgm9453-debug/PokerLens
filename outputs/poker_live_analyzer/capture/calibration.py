"""手動辨識區域的比例座標、驗證簽章與獨立設定檔。"""

from dataclasses import dataclass, replace
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import tempfile

from .profiles import Region


SCHEMA_VERSION = 1
_FIELDS = {'schema_version', 'regions', 'reference_size', 'seat_layout', 'locked', 'verified_signature'}
_COORDINATES = ('x', 'y', 'width', 'height')


def _seats(layout):
    if type(layout) is not int or layout not in (6, 8):
        raise ValueError('辨識位置只支援六人或八人座位配置')
    return (0, 1, 3, 4, 5, 7) if layout == 6 else tuple(range(8))


def region_labels(layout=8) -> dict[str, str]:
    """列出此版型可框選的區域，英雄籌碼只保留一個欄位。"""
    seats = _seats(layout)
    labels = {
        'hero': '自身底牌',
        'board': '公共牌',
        'pot': '底池金額',
        'call_amount': '跟注金額',
        'hero_stack': '自身剩餘籌碼',
    }
    for seat in seats:
        subject = '自身' if seat == 0 else f'座位 {seat}'
        labels[f'bet_{seat}'] = f'{subject}下注金額'
        if seat != 0:
            labels[f'stack_{seat}'] = f'{subject}剩餘籌碼'
            labels[f'back_{seat}'] = f'{subject}牌背'
        labels[f'chips_{seat}'] = f'{subject}下注籌碼區域（選填）'
    return labels


def default_regions(layout=8) -> dict[str, Region]:
    """需要預設位置時才載入辨識器，設定讀取不依賴影像套件。"""
    _seats(layout)
    from vision.card_detector import HERO_REGION, BOARD_REGION
    from vision.player_detector import SEAT_REGIONS, SIX_SEAT_REGIONS
    from vision.table_detector import (
        POT_ROI, HERO_STACK_ROI, CALL_ROI, BET_ROIS, STACK_ROIS, CHIP_ROIS,
        SIX_BET_ROIS, SIX_STACK_ROIS, SIX_CHIP_ROIS,
    )

    bets, stacks, chips, backs = (
        (SIX_BET_ROIS, SIX_STACK_ROIS, SIX_CHIP_ROIS, SIX_SEAT_REGIONS)
        if layout == 6 else (BET_ROIS, STACK_ROIS, CHIP_ROIS, SEAT_REGIONS)
    )
    regions = {
        'hero': Region(*HERO_REGION),
        'board': Region(*BOARD_REGION),
        'pot': Region(*POT_ROI),
        'call_amount': Region(*CALL_ROI),
        'hero_stack': Region(*HERO_STACK_ROI),
    }
    regions.update({f'bet_{seat}': Region(*roi) for seat, roi in bets.items()})
    regions.update({f'stack_{seat}': Region(*roi) for seat, roi in stacks.items() if seat != 0})
    regions.update({f'back_{seat}': Region(*roi) for seat, roi in backs.items()})
    regions.update({f'chips_{seat}': Region(*roi) for seat, roi in chips.items()})
    return regions


def _size(size):
    if (not isinstance(size, (tuple, list)) or len(size) != 2
            or any(type(value) is not int or value <= 0 for value in size)):
        raise ValueError('牌桌尺寸必須是兩個正整數')
    return tuple(size)


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _region_values(region):
    if not isinstance(region, Region):
        raise ValueError('辨識區域必須使用有效的比例座標')
    values = tuple(getattr(region, name) for name in _COORDINATES)
    if not all(_finite_number(value) for value in values):
        raise ValueError('辨識區域座標必須是有限數值，不能使用布林值')
    Region(*values)
    return {name: float(value) for name, value in zip(_COORDINATES, values)}


@dataclass(frozen=True)
class CalibrationProfile:
    regions: dict[str, Region]
    reference_size: tuple[int, int]
    seat_layout: int = 8
    locked: bool = False
    verified_signature: str = ''

    def __post_init__(self):
        labels = region_labels(self.seat_layout)
        if not isinstance(self.regions, dict):
            raise ValueError('辨識位置設定的區域必須是字典')
        for name, region in self.regions.items():
            if not isinstance(name, str) or name not in labels:
                raise ValueError('辨識位置設定包含未知區域或此版型不存在的座位')
            _region_values(region)
        if type(self.locked) is not bool:
            raise ValueError('辨識位置設定的鎖定狀態必須是布林值')
        if not isinstance(self.verified_signature, str):
            raise ValueError('辨識位置設定的驗證簽章必須是文字')
        object.__setattr__(self, 'regions', dict(self.regions))
        object.__setattr__(self, 'reference_size', _size(self.reference_size))
        if self.locked:
            self._assert_verified()

    @property
    def signature(self) -> str:
        geometry = {
            'regions': {name: _region_values(region) for name, region in self.regions.items()},
            'reference_size': self.reference_size,
            'seat_layout': self.seat_layout,
        }
        encoded = json.dumps(geometry, sort_keys=True, separators=(',', ':'), allow_nan=False)
        return sha256(encoded.encode('utf-8')).hexdigest()

    @property
    def verified(self) -> bool:
        return bool(self.regions) and bool(self.verified_signature) and self.verified_signature == self.signature

    def _assert_verified(self):
        if not self.regions:
            raise ValueError('尚未框選任何辨識區域，無法鎖定或驗證')
        if not self.verified:
            raise ValueError('辨識位置尚未通過驗證或已變更，請重新驗證後鎖定')

    def with_region(self, name: str, region: Region):
        regions = dict(self.regions)
        regions[name] = region
        return replace(self, regions=regions, locked=False, verified_signature='')

    def mark_verified(self):
        if not self.regions:
            raise ValueError('尚未框選任何辨識區域，無法驗證')
        return replace(self, verified_signature=self.signature)

    def lock(self):
        self._assert_verified()
        return replace(self, locked=True)

    def unlock(self):
        return replace(self, locked=False, verified_signature='')

    def assert_compatible(self, size: tuple[int, int]):
        width, height = _size(size)
        reference_width, reference_height = self.reference_size
        difference = abs(width * reference_height - height * reference_width)
        if difference * 100 > height * reference_width * 3:
            raise ValueError('牌桌長寬比例已變更超過百分之三，請重新校準辨識位置')


class CalibrationStore:
    def __init__(self, path):
        self.path = Path(path)

    def load(self) -> CalibrationProfile | None:
        try:
            content = self.path.read_text(encoding='utf-8')
        except FileNotFoundError:
            return None
        except UnicodeError as error:
            raise ValueError('辨識位置設定檔文字毀損，請重新校準') from error
        except OSError as error:
            raise OSError('無法讀取辨識位置設定檔') from error
        try:
            data = json.loads(content)
        except (ValueError, RecursionError) as error:
            raise ValueError('辨識位置設定檔毀損，請重新校準') from error
        if not isinstance(data, dict) or set(data) != _FIELDS:
            raise ValueError('辨識位置設定欄位不完整或包含未知欄位')
        if type(data['schema_version']) is not int or data['schema_version'] != SCHEMA_VERSION:
            raise ValueError('未知的辨識位置設定格式版本，請重新校準')
        labels = region_labels(data['seat_layout'])
        if not isinstance(data['regions'], dict):
            raise ValueError('辨識位置設定的區域必須是字典')
        regions = {}
        for name, coordinates in data['regions'].items():
            if name not in labels:
                raise ValueError('辨識位置設定包含未知區域或此版型不存在的座位')
            if not isinstance(coordinates, dict) or set(coordinates) != set(_COORDINATES):
                raise ValueError(f'{labels[name]}的設定座標不完整或格式錯誤')
            values = tuple(coordinates[key] for key in _COORDINATES)
            if not all(_finite_number(value) for value in values):
                raise ValueError(f'{labels[name]}的設定座標必須是有限數值')
            regions[name] = Region(*values)
        return CalibrationProfile(
            regions=regions,
            reference_size=_size(data['reference_size']),
            seat_layout=data['seat_layout'],
            locked=data['locked'],
            verified_signature=data['verified_signature'],
        )

    def save(self, profile: CalibrationProfile):
        if not isinstance(profile, CalibrationProfile):
            raise ValueError('只能儲存有效的辨識位置設定')
        # 重新檢查外部修改過的字典，避免保存已失效的鎖定簽章。
        profile = replace(profile)
        data = {
            'schema_version': SCHEMA_VERSION,
            'regions': {name: _region_values(region) for name, region in profile.regions.items()},
            'reference_size': list(profile.reference_size),
            'seat_layout': profile.seat_layout,
            'locked': profile.locked,
            'verified_signature': profile.verified_signature,
        }
        temporary_path = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', dir=self.path.parent,
                prefix=f'.{self.path.name}.', suffix='.tmp', delete=False,
            ) as output:
                temporary_path = Path(output.name)
                json.dump(data, output, ensure_ascii=False, indent=2, allow_nan=False)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, self.path)
        except OSError as error:
            raise OSError('無法儲存辨識位置設定，原設定檔已保留') from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
