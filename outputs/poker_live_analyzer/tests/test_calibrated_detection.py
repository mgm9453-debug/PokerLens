"""固定位置須真正讀取手框，未知畫面不能通過校準。"""
import asyncio
from pathlib import Path
import sys
import cv2
import numpy as np
import pytest
from capture.profiles import Region


def profile(regions, size=(1128, 799), layout=8, locked=False):
    from capture.calibration import CalibrationProfile
    result = CalibrationProfile(regions, size, seat_layout=layout)
    return result.mark_verified().lock() if locked else result


def frame():
    image = np.full((799, 1128, 3), 90, np.uint8)
    image[:80, :80] = 180
    return image


class PixelOcr:
    async def read_amount(self, image):
        value = int(image[0, 0, 0])
        return float(value) if value in (100, 125, 150) else None


def validate(config, images, ocr=None):
    from vision.calibrated_detection import validate_calibration
    return asyncio.run(validate_calibration(config, images, ocr=ocr))


def test_locked_factory_reads_moved_amount_pixels():
    from vision.calibrated_detection import build_detectors
    from vision.table_detector import crop
    image = frame()
    region = Region(.1, .12, .18, .08)
    crop(image, (region.x, region.y, region.width, region.height))[:] = 125
    cards, players, money = build_detectors(profile({'pot': region}, locked=True), ocr=PixelOcr())
    result = asyncio.run(money.detect(image))
    assert result.pot == 125
    assert players.seat_layout == 8


def test_unlocked_factory_keeps_automatic_regions():
    from vision.calibrated_detection import build_detectors
    from vision.table_detector import POT_ROI
    from vision.card_detector import HERO_REGION
    cards, _, money = build_detectors(profile({'pot': Region(.1, .1, .2, .1)}))
    assert money.pot_roi == POT_ROI
    assert cards.hero_region == HERO_REGION


def test_locked_factory_refuses_signature_changed_by_external_mutation():
    from vision.calibrated_detection import build_detectors
    config = profile({'pot': Region(.1, .1, .1, .1)}, locked=True)
    config.regions['pot'] = Region(.2, .2, .1, .1)
    assert config.locked and not config.verified
    with pytest.raises(ValueError, match='校準'):
        build_detectors(config)


def test_six_seat_factory_cannot_replace_custom_geometry():
    from vision.calibrated_detection import build_detectors
    region = Region(.1, .1, .1, .1)
    _, players, money = build_detectors(profile({'bet_3': region}, layout=6, locked=True))
    money.set_seat_layout(8)
    assert players.seat_layout == 6
    assert set(money.bet_rois) == {0, 1, 3, 4, 5, 7}
    assert money.bet_rois[3] == (.1, .1, .1, .1)
    assert 3 not in money.chip_rois


def test_custom_empty_bet_requires_related_chip_region():
    from vision.calibrated_detection import build_detectors
    config = profile({'bet_3': Region(.1, .1, .1, .1)}, locked=True)
    _, _, money = build_detectors(config, ocr=PixelOcr())
    result = asyncio.run(money.detect(frame()))
    assert 3 not in result.seat_bets
    related = profile({'bet_3': Region(.1, .1, .1, .1), 'chips_3': Region(.1, .05, .1, .05)}, locked=True)
    _, _, money = build_detectors(related, ocr=PixelOcr())
    result = asyncio.run(money.detect(frame()))
    assert result.seat_bets[3] == 0


def test_black_custom_chip_region_cannot_confirm_zero_bet():
    from vision.calibrated_detection import build_detectors
    from vision.table_detector import crop
    config = profile({'bet_3': Region(.1, .1, .1, .1), 'chips_3': Region(.1, .05, .1, .04)}, locked=True)
    image = frame()
    crop(image, (.1, .05, .1, .04))[:] = 0
    _, _, money = build_detectors(config, ocr=PixelOcr())
    result = asyncio.run(money.detect(image))
    assert 3 not in result.seat_bets
    checked = validate(config, [image] * 3, PixelOcr())
    assert not checked.valid
    assert 'bet_3' in checked.errors


def test_custom_back_frame_is_exact_and_does_not_change_layout(monkeypatch):
    from vision.calibrated_detection import build_detectors
    region = Region(.1, .1, .08, .06)
    _, players, _ = build_detectors(profile({'back_3': region}, layout=6, locked=True))
    seen = []
    def state(image, height):
        seen.append(image.shape[:2])
        return 'empty'
    monkeypatch.setattr(players, 'green_state', state)
    assert players.detect(frame()).reliable
    assert players.seat_layout == 6
    height, width = frame().shape[:2]
    exact = (round(.16 * height) - round(.1 * height), round(.18 * width) - round(.1 * width))
    assert exact in seen
    assert len(seen) == 5


def test_validate_only_selected_amount_and_requires_three_frames():
    config = profile({'pot': Region(.1, .1, .1, .1)})
    image = frame()
    image[79:160, 112:227] = 125
    incomplete = validate(config, [image, image], PixelOcr())
    assert not incomplete.valid
    result = validate(config, [image] * 3, PixelOcr())
    assert result.valid, result.errors
    assert result.readings == {'pot': '125'}
    assert result.signature == config.signature


def test_validate_rejects_wrong_pot_even_when_global_locator_finds_amount():
    class Ocr(PixelOcr):
        async def locate_pot(self, image):
            return 125
    result = validate(profile({'pot': Region(.1, .1, .1, .1)}), [frame()] * 3, Ocr())
    assert not result.valid
    assert 'pot' in result.errors


def test_locked_pot_does_not_read_outside_custom_frame():
    from vision.calibrated_detection import build_detectors
    class Ocr(PixelOcr):
        async def locate_pot(self, image):
            return 125
    _, _, money = build_detectors(profile({'pot': Region(.1, .1, .1, .1)}, locked=True), ocr=Ocr())
    result = asyncio.run(money.detect(frame()))
    assert result.pot is None


def test_locked_default_call_frame_does_not_use_adjacent_number_region():
    from vision.calibrated_detection import build_detectors
    from vision.table_detector import crop, CALL_ROI, CALL_NUMBER_ROI, HERO_STACK_ROI, POT_ROI
    image = frame()
    crop(image, HERO_STACK_ROI)[:] = 100
    crop(image, POT_ROI)[:] = 150
    crop(image, CALL_NUMBER_ROI)[:] = 125
    _, _, money = build_detectors(profile({'call_amount': Region(*CALL_ROI)}, locked=True), ocr=PixelOcr())
    result = asyncio.run(money.detect(image))
    assert result.call_amount is None


def test_custom_bet_does_not_expand_into_unselected_pixels():
    from vision.calibrated_detection import build_detectors
    from vision.ocr_engine import NativeOcrEngine, OcrText
    class Ocr(NativeOcrEngine):
        def __init__(self):
            self.bb_display = False
            self.big_blind = None
        async def read_amount(self, image):
            return 125 if image.shape[0] == 80 and image.shape[1] > 150 else None
        async def read_pot_amount(self, image):
            return None
        async def recognize(self, image):
            return OcrText('', True)
    _, _, money = build_detectors(profile({'bet_3': Region(.1, .1, .1, .1)}, locked=True), ocr=Ocr())
    result = asyncio.run(money.detect(frame()))
    assert 3 not in result.seat_bets


def test_validate_rejects_unknown_call_despite_table_bet_difference():
    result = validate(profile({'call_amount': Region(.1, .1, .1, .1)}), [frame()] * 3, PixelOcr())
    assert not result.valid
    assert '跟注' in result.errors['call_amount']


def test_validate_accepts_explicit_check_button():
    from vision.ocr_engine import OcrText
    class Ocr(PixelOcr):
        async def recognize(self, image):
            return OcrText('過牌', True)
    result = validate(profile({'call_amount': Region(.1, .1, .1, .1)}), [frame()] * 3, Ocr())
    assert result.valid, result.errors
    assert result.readings['call_amount'] == '0'


def test_locked_call_reads_explicit_check_without_table_bet_inference():
    from vision.calibrated_detection import build_detectors
    from vision.ocr_engine import OcrText
    class Ocr(PixelOcr):
        async def recognize(self, image):
            return OcrText('過牌', True)
    _, _, money = build_detectors(profile({'call_amount': Region(.1, .1, .1, .1)}, locked=True), ocr=Ocr())
    result = asyncio.run(money.detect(frame()))
    assert result.call_amount == 0
    assert not result.reliable


def test_locked_call_missing_cannot_be_replaced_by_other_bet_regions():
    from vision.calibrated_detection import build_detectors
    from vision.table_detector import crop
    region=Region(.1,.1,.1,.1)
    image=np.full((799,1128,3),100,np.uint8)
    crop(image,(region.x,region.y,region.width,region.height))[:]=90
    _,_,money=build_detectors(profile({'call_amount':region},locked=True),ocr=PixelOcr())
    result=asyncio.run(money.detect(image))
    assert result.call_amount is None
    assert not result.field_reliable['call_amount']


def test_missing_custom_call_does_not_compare_unknown_with_native_ocr_expected_amount():
    from vision.calibrated_detection import build_detectors
    from vision.ocr_engine import NativeOcrEngine,OcrText
    from vision.table_detector import crop
    class Ocr(PixelOcr,NativeOcrEngine):
        def __init__(self):
            self.bb_display=False
            self.big_blind=None
        async def read_pot_amount(self,image):
            return await self.read_amount(image)
        async def recognize(self,image):
            return OcrText('',True)
        async def read_amount_matching(self,image,expected):
            pytest.fail('未知跟注額不能進入金額比對')
    region=Region(.1,.1,.1,.1)
    image=np.full((799,1128,3),100,np.uint8)
    crop(image,(region.x,region.y,region.width,region.height))[:]=90
    _,_,money=build_detectors(profile({'call_amount':region},locked=True),ocr=Ocr())
    result=asyncio.run(money.detect(image))
    assert result.call_amount is None


def test_validate_rejects_same_card_in_selected_hero_and_board(monkeypatch):
    from types import SimpleNamespace
    import vision.calibrated_detection as module
    from vision.table_detector import crop
    hero=Region(.1,.1,.1,.1)
    board=Region(.4,.4,.2,.1)
    image=frame()
    crop(image,(hero.x,hero.y,hero.width,hero.height))[:]=100
    crop(image,(board.x,board.y,board.width,board.height))[:]=150
    class Cards:
        def find_cards(self,image):
            cards=['As','Ks'] if image[0,0,0]==100 else ['As','Qd','Jh']
            return cards,[1.0]*len(cards),False
    monkeypatch.setattr(module,'build_detectors',lambda *args,**kwargs:(Cards(),None,SimpleNamespace()))
    result=validate(profile({'hero':hero,'board':board}),[image]*3)
    assert not result.valid
    assert '重複' in result.errors['hero']
    assert '重複' in result.errors['board']


@pytest.mark.parametrize('text', ['等待過牌', '不可過牌', 'check 100', ''])
def test_validate_rejects_non_button_check_text(text):
    from vision.ocr_engine import OcrText
    class Ocr(PixelOcr):
        async def recognize(self, image):
            return OcrText(text, True)
    result = validate(profile({'call_amount': Region(.1, .1, .1, .1)}), [frame()] * 3, Ocr())
    assert not result.valid


def test_validate_rejects_hero_without_two_visible_cards():
    result = validate(profile({'hero': Region(.1, .1, .1, .1)}), [frame()] * 3)
    assert not result.valid
    assert '兩張' in result.errors['hero']


def test_validate_accepts_empty_preflop_board():
    result = validate(profile({'board': Region(.1, .1, .1, .1)}), [frame()] * 3)
    assert result.valid, result.errors
    assert result.readings['board'] == '翻前無公共牌'


def test_validate_hero_reads_cards_moved_out_of_default_region():
    from card_rendering import load_faces, render_pair
    from vision.card_detector import crop_region, HERO_REGION
    original = render_pair('Ad', 'Ks', load_faces())
    hero = crop_region(original, HERO_REGION).copy()
    image = frame()
    region = Region(.05, .05, HERO_REGION[2], HERO_REGION[3])
    target = crop_region(image, (region.x, region.y, region.width, region.height))
    target[:] = cv2.resize(hero, (target.shape[1], target.shape[0]))
    result = validate(profile({'hero': region}), [image] * 3)
    assert result.valid, result.errors
    assert result.readings['hero'] == 'Ad Ks'


def test_validate_rejects_duplicate_between_selected_hero_and_board():
    from card_rendering import load_faces, render_pair
    from vision.card_detector import crop_region, HERO_REGION, BOARD_REGION
    original = render_pair('Ad', 'Ks', load_faces())
    board_frame = cv2.imread(str(Path(__file__).parent / 'fixtures' / 'board_anonymous.png'))
    image = frame()
    regions = {'hero': Region(.05, .05, HERO_REGION[2], HERO_REGION[3]),
        'board': Region(.3, .3, BOARD_REGION[2], BOARD_REGION[3])}
    for key, source in [('hero', crop_region(original, HERO_REGION)), ('board', crop_region(board_frame, BOARD_REGION))]:
        region = regions[key]
        target = crop_region(image, (region.x, region.y, region.width, region.height))
        target[:] = cv2.resize(source, (target.shape[1], target.shape[0]))
    result = validate(profile(regions), [image] * 3)
    assert not result.valid
    assert 'hero' in result.errors and 'board' in result.errors


@pytest.mark.skipif(sys.platform != 'win32', reason='需要原生文字辨識')
def test_native_amount_validation_reads_moved_textured_pot():
    from vision.table_detector import crop, POT_ROI
    original = cv2.imread(str(Path(__file__).parent / 'fixtures' / 'wood_amounts_anonymous.png'))
    image = np.full_like(original, 90)
    region = Region(.05, .05, POT_ROI[2], POT_ROI[3])
    target = crop(image, (region.x, region.y, region.width, region.height))
    source = crop(original, POT_ROI)
    target[:] = cv2.resize(source, (target.shape[1], target.shape[0]))
    result = validate(profile({'pot': region}, size=(image.shape[1], image.shape[0])), [image] * 3)
    assert result.valid, result.errors
    assert result.readings['pot'] == '127366'


def test_validate_back_accepts_confirmed_empty_but_black_is_unknown():
    region = Region(.1, .1, .1, .1)
    image = frame()
    assert validate(profile({'back_3': region}), [image] * 3).valid
    image[79:160, 112:227] = 0
    result = validate(profile({'back_3': region}), [image] * 3)
    assert not result.valid
    assert 'back_3' in result.errors


def test_back_validation_uses_same_pixel_boundary_as_live_detection(monkeypatch):
    from vision.player_detector import PlayerDetector
    region = Region(.1006, .1006, .0802, .0602)
    seen = []
    def state(self, image, height):
        seen.append(image.shape[:2])
        return 'empty'
    monkeypatch.setattr(PlayerDetector, 'green_state', state)
    result = validate(profile({'back_3': region}), [frame()] * 3)
    assert result.valid
    expected = (round((region.y + region.height) * 799) - round(region.y * 799),
        round((region.x + region.width) * 1128) - round(region.x * 1128))
    assert seen == [expected] * 3


def test_failed_field_reader_returns_validation_error():
    class Ocr(PixelOcr):
        async def read_amount(self, image):
            raise RuntimeError('文字辨識暫時不可用')
    result = validate(profile({'pot': Region(.1, .1, .1, .1)}), [frame()] * 3, Ocr())
    assert not result.valid
    assert 'pot' in result.errors


def test_validate_rejects_unstable_amounts():
    from vision.table_detector import crop
    config = profile({'pot': Region(.1, .1, .1, .1)})
    images = []
    for value in (100, 125, 150):
        image = frame()
        crop(image, (.1, .1, .1, .1))[:] = value
        images.append(image)
    assert not validate(config, images, PixelOcr()).valid


def test_validate_rejects_changed_aspect_ratio_and_accepts_uniform_scaling():
    from vision.table_detector import crop
    config = profile({'pot': Region(.1, .1, .1, .1)})
    image = frame()
    crop(image, (.1, .1, .1, .1))[:] = 125
    scaled = cv2.resize(image, (2256, 1598))
    assert validate(config, [scaled] * 3, PixelOcr()).valid
    changed = cv2.resize(image, (900, 799))
    result = validate(config, [changed] * 3, PixelOcr())
    assert not result.valid
    assert '比例' in result.errors['pot']
