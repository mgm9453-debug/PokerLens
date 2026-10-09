"""以相同的固定區域建立即時辨識器與逐欄校準驗證。"""
from dataclasses import dataclass
import cv2
import numpy as np
from capture.calibration import default_regions, region_labels
from vision.card_detector import CardDetector
from vision.player_detector import PlayerDetector
from vision.table_detector import TableDetector, crop, chip_evidence, empty_bet_evidence, textured_empty_bet


@dataclass(frozen=True)
class CalibrationValidation:
    valid: bool
    readings: dict[str, str]
    errors: dict[str, str]
    signature: str


def calibration_active(profile):
    return profile is not None and profile.locked and profile.verified


def _coordinates(region):
    return region.x, region.y, region.width, region.height


def build_detectors(profile=None, require_locked=True, ocr=None):
    if profile is not None and profile.locked and not profile.verified:
        raise ValueError('鎖定的辨識位置已變更，請重新校準並驗證')
    if profile is None or (require_locked and not calibration_active(profile)):
        return CardDetector(), PlayerDetector(green_only=True), TableDetector(ocr=ocr)
    regions = {**default_regions(profile.seat_layout), **profile.regions}
    positions = {key: _coordinates(region) for key, region in regions.items()}
    def seats(prefix):
        return {int(key.split('_')[1]): region for key, region in positions.items() if key.startswith(prefix + '_')}
    chips = seats('chips')
    # 自訂數字框不能沿用其他位置的籌碼證據；未框籌碼時保留空下注未知。
    for key in profile.regions:
        if key.startswith('bet_') and key.replace('bet_', 'chips_', 1) not in profile.regions:
            chips.pop(int(key.split('_')[1]), None)
    cards = CardDetector(hero_region=positions['hero'], board_region=positions['board'])
    players = PlayerDetector(green_only=True, regions=seats('back'), seat_layout=profile.seat_layout,
        exact_seats={int(key.split('_')[1]) for key in profile.regions if key.startswith('back_')})
    money = TableDetector(ocr=ocr, pot_roi=positions['pot'], hero_stack_roi=positions['hero_stack'],
        call_roi=positions['call_amount'], bet_rois=seats('bet'), stack_rois={0: positions['hero_stack'], **seats('stack')},
        chip_rois=chips, seat_layout=profile.seat_layout, exact_fields=profile.regions)
    return cards, players, money


def _clear_image(image):
    if image is None or not image.size:
        return False
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return 15 < float(gray.mean()) < 235 and float(gray.max()) >= 30


async def _read_amount(key, image, money):
    reader = money.ocr.read_pot_amount if key == 'pot' and hasattr(money.ocr, 'read_pot_amount') else money.ocr.read_amount
    value = await reader(image)
    if value is not None and (not np.isfinite(value) or value < 0):
        value = None
    if value is None and key == 'call_amount' and hasattr(money.ocr, 'recognize'):
        text = await money.ocr.recognize(cv2.resize(image, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC))
        label = ''.join(text.text.lower().split()) if text.available else ''
        if label in ('過牌', '过牌', 'check'):
            value = 0.0
    if value is None and key.startswith('stack_') and hasattr(money.ocr, 'recognize'):
        text = await money.ocr.recognize(cv2.resize(image, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC))
        label = ''.join(text.text.lower().split()) if text.available else ''
        if label in ('全下', 'allin', 'all-in'):
            value = 0.0
    return value


async def _read_field(key, frame, roi, cards, players, money):
    image = crop(frame, roi)
    if key.startswith('back_'):
        height, width = frame.shape[:2]
        x, y, rw, rh = roi
        image = frame[round(y * height):round((y + rh) * height), round(x * width):round((x + rw) * width)]
    if not _clear_image(image):
        return None
    if key in ('hero', 'board'):
        values, scores, uncertain = cards.find_cards(image)
        allowed = (2,) if key == 'hero' else (0, 3, 4, 5)
        if uncertain or len(values) not in allowed or len(set(values)) != len(values) or (scores and min(scores) < .85):
            return None
        return ' '.join(values) if values else '翻前無公共牌'
    if key.startswith('back_'):
        state = players.green_state(image, frame.shape[0])
        return {'active': '已確認綠色牌背', 'empty': '已確認無牌背'}.get(state)
    if key.startswith('chips_'):
        if chip_evidence(image):
            return '已確認籌碼筆畫'
        if empty_bet_evidence(image) or textured_empty_bet(image, image):
            return '已確認無籌碼'
        return None
    value = await _read_amount(key, image, money)
    if value is None and key.startswith('bet_'):
        chip_roi = money.chip_rois.get(int(key.split('_')[1]))
        if chip_roi is not None:
            chips = crop(frame, chip_roi)
            if (not chip_evidence(chips) and empty_bet_evidence(chips) and empty_bet_evidence(image)) or textured_empty_bet(image, chips):
                value = 0.0
    return format(value, 'g') if value is not None else None


async def validate_calibration(profile, frames, ocr=None):
    signature = profile.signature
    keys = tuple(profile.regions)
    if not keys:
        return CalibrationValidation(False, {}, {'regions': '請先框選需要校準的辨識區域'}, signature)
    images = list(frames)
    if len(images) < 3:
        return CalibrationValidation(False, {}, {key: '至少需要三幀畫面一致確認' for key in keys}, signature)
    for image in images:
        try:
            if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] != 3 or not image.size:
                raise ValueError('缺少有效牌桌影格')
            profile.assert_compatible((image.shape[1], image.shape[0]))
        except ValueError as error:
            return CalibrationValidation(False, {}, {key: str(error) for key in keys}, signature)
    cards, players, money = build_detectors(profile, require_locked=False, ocr=ocr)
    previous, counts, readings = {}, {}, {}
    for image in images:
        for key in keys:
            try:
                value = await _read_field(key, image, _coordinates(profile.regions[key]), cards, players, money)
            except (ValueError, RuntimeError, OSError, cv2.error):
                value = None
            counts[key] = counts.get(key, 0) + 1 if value is not None and previous.get(key) == value else (1 if value is not None else 0)
            previous[key] = value
            if value is not None:
                readings[key] = value
            else:
                readings.pop(key, None)
    labels = region_labels(profile.seat_layout)
    errors = {}
    for key in keys:
        if counts.get(key, 0) < 3:
            detail = '；請等待兩張完整底牌' if key == 'hero' else ''
            if key.startswith('bet_') and key.replace('bet_', 'chips_', 1) not in profile.regions:
                detail = '；若要確認無下注，請一併框選該座位籌碼區域'
            errors[key] = f'請校準{labels.get(key, key)}區域，讀取尚未連續三幀確認{detail}'
    if 'hero' in readings and 'board' in readings and readings['board'] != '翻前無公共牌':
        if set(readings['hero'].split()) & set(readings['board'].split()):
            errors['hero'] = errors['board'] = '底牌與公共牌出現重複牌面，請重新校準兩個區域'
    return CalibrationValidation(not errors, readings, errors, signature)
