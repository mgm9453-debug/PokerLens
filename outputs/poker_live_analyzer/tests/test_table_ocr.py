import asyncio
from pathlib import Path
import sys
import cv2
import numpy as np
import pytest
from vision.ocr_engine import NativeOcrEngine, parse_amount
from vision.table_detector import TableDetector, BET_ROIS, CHIP_ROIS

def test_strict_amount_parse():
    assert parse_amount('9,240')==9240
    assert parse_amount('555')==555
    assert parse_amount('跟注 185')==185
    assert parse_amount('') is None
    assert parse_amount('1O0') is None
    assert parse_amount('-10') is None
    assert parse_amount('100 200') is None

@pytest.mark.parametrize('color',[(180,110,40),(45,65,48),(60,95,135),(90,90,90)])
def test_empty_bet_does_not_depend_on_table_color(color):
    from vision.table_detector import empty_bet_evidence,chip_evidence
    image=np.full((37,70,3),color,np.uint8)
    assert empty_bet_evidence(image)
    assert not chip_evidence(image)
    cv2.putText(image,'800',(4,28),cv2.FONT_HERSHEY_SIMPLEX,.7,(240,240,240),2)
    assert not empty_bet_evidence(image)
    assert chip_evidence(image)

def test_black_unknown_region_is_not_zero_bet():
    from vision.table_detector import empty_bet_evidence
    assert not empty_bet_evidence(np.zeros((37,70,3),np.uint8))

def test_matching_amount_never_rewrites_an_unconfirmed_decimal():
    from vision.ocr_engine import OcrText
    class Ocr(NativeOcrEngine):
        def __init__(self):self.big_blind=None;self.bb_display=False
        async def recognize(self,image):return OcrText('6.366',True)
    image=np.full((32,100,3),90,np.uint8)
    assert asyncio.run(Ocr().read_amount_matching(image,6366)) is None

def test_tiny_table_texture_is_not_a_missing_bet():
    from vision.table_detector import empty_bet_evidence
    image=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/empty_bet_texture.png',np.uint8),1)
    assert empty_bet_evidence(image)
    # 空區能忽略微小紋理，真正的數字筆畫仍須拒絕當成零。
    cv2.putText(image,'1',(18,32),cv2.FONT_HERSHEY_SIMPLEX,.7,(240,240,240),1)
    assert not empty_bet_evidence(image)

def test_thin_avatar_border_does_not_block_empty_bet():
    from vision.table_detector import empty_bet_evidence
    image=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/empty_bet_border.png',np.uint8),1)
    assert empty_bet_evidence(image)
    cv2.putText(image,'80',(20,30),cv2.FONT_HERSHEY_SIMPLEX,.7,(240,240,240),2)
    assert not empty_bet_evidence(image)

@pytest.mark.skipif(sys.platform!='win32',reason='需要原生文字辨識')
def test_visible_turn_button_recovers_after_empty_border_and_punctuation():
    image=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/turn_button_amounts_anonymous.png',np.uint8),1)
    async def check():
        detector=TableDetector(big_blind=3000)
        for _ in range(3):result=await detector.detect(image)
        assert result.reliable,result.reason
        assert result.pot==13266
        assert result.hero_stack==26450
        assert result.seat_bets[1]==0
        assert result.seat_bets[7]==6366
        assert result.call_amount==6366
    asyncio.run(check())

def test_texture_does_not_block_stable_call_difference():
    from vision.table_detector import crop
    image=np.full((909,1302,3),90,np.uint8)
    region=crop(image,BET_ROIS[7])
    region[:]=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/empty_bet_texture.png',np.uint8),1)
    class Ocr:
        def __init__(self):self.index=0
        async def read_amount(self,image):
            values=[4600,27150,None,1000,2000]+[None]*6+[10000]*7
            value=values[self.index%len(values)];self.index+=1
            return value
    async def check():
        detector=TableDetector(ocr=Ocr(),call_roi=(0,0,.1,.1))
        results=[await detector.detect(image) for _ in range(3)]
        assert not results[0].reliable
        result=results[-1]
        assert result.reliable,result.reason
        assert result.seat_bets[7]==0
        assert result.call_amount==1000
    asyncio.run(check())

def test_inconsistent_pot_reports_values_and_stays_unreliable():
    class Ocr:
        def __init__(self): self.index=0
        async def read_amount(self,image):
            values=[500,1000,100]+[100]*8+[1000]*7
            value=values[self.index%len(values)]
            self.index+=1
            return value
    async def check():
        detector=TableDetector(ocr=Ocr())
        for _ in range(3): result=await detector.detect(np.full((799,1128,3),90,np.uint8))
        assert not result.reliable
        assert '底池 500' in result.reason and '下注合計 800' in result.reason
    asyncio.run(check())

@pytest.mark.skipif(sys.platform!='win32',reason='需要原生文字辨識')
def test_wider_lower_call_region_reads_visible_call_number():
    from vision.table_detector import CALL_NUMBER_ROI,crop
    image=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/跟注數字匿名.png',np.uint8),1)
    frame=np.zeros((779,1112,3),np.uint8)
    target=crop(frame,CALL_NUMBER_ROI)
    target[:]=image
    result=asyncio.run(TableDetector().detect(frame))
    assert result.call_amount==1154
    assert not result.reliable

@pytest.mark.skipif(sys.platform!='win32',reason='原生文字辨識僅支援視窗作業系統')
def test_real_native_ocr_and_multiframe():
    image=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures'/'amounts_anonymous.png',np.uint8),1)
    async def check():
        detector=TableDetector(stable_frames=3)
        results=[await detector.detect(image) for _ in range(3)]
        assert not results[0].reliable
        result=results[-1]
        assert result.reliable, result.reason
        assert (result.pot,result.hero_stack,result.call_amount)==(555,9240,185)
        assert result.seat_bets=={0:100,1:0,2:285,3:0,4:0,5:0,6:0,7:50}
        assert result.seat_stacks=={0:9240,1:9955,2:9055,3:9955,4:10352,5:9280,6:12318,7:9290}
        blank=await detector.detect(np.zeros_like(image))
        assert not blank.reliable
        assert blank.pot is None and blank.call_amount is None
        assert 1 not in blank.seat_bets
    asyncio.run(check())

def test_lowcontrast_texture_at_pixel_boundary_is_empty():
    from vision.table_detector import empty_bet_evidence
    image=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/empty_bet_lowcontrast_texture.png',np.uint8),1)
    assert empty_bet_evidence(image)
    written=image.copy()
    cv2.putText(written,'150',(15,26),cv2.FONT_HERSHEY_SIMPLEX,.65,(210,210,210),1)
    assert not empty_bet_evidence(written)


def test_chip_with_missing_amount_never_becomes_zero():
    image=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures'/'amounts_anonymous.png',np.uint8),1)
    h,w=image.shape[:2]
    x,y,rw,rh=BET_ROIS[2]
    # 只清除數字，保留上方紅色籌碼，模擬畫面遮擋。
    image[int(y*h):int((y+rh)*h),int(x*w):int((x+rw)*w)]=(180,110,40)
    async def check():
        detector=TableDetector()
        for _ in range(3): result=await detector.detect(image)
        assert 2 not in result.seat_bets
        assert not result.reliable
    asyncio.run(check())


@pytest.mark.skipif(sys.platform!='win32',reason='需要原生文字辨識')
def test_break_overlay_is_waiting_not_a_hand():
    image=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/break_anonymous.png',np.uint8),1)
    result=asyncio.run(TableDetector().detect(image))
    assert result.paused
    assert not result.reliable
    assert '休息' in result.reason
def test_six_seat_amounts_and_empty_bets_share_the_layout():
    image=cv2.imread(str(Path(__file__).parent/'fixtures/six_amounts_anonymous.png'))
    async def check():
        detector=TableDetector()
        detector.set_seat_layout(6)
        for _ in range(3):result=await detector.detect(image)
        assert result.reliable,result.reason
        assert result.seats==(0,1,3,4,5,7)
        assert result.pot==13600
        assert result.hero_stack==136475
        assert result.call_amount==0
        assert result.seat_bets=={0:4000,1:0,3:4000,4:0,5:0,7:2000}
        detector.set_seat_layout(8)
        assert set(detector.bet_rois)==set(range(8))
        assert detector.previous=={}
    asyncio.run(check())


def test_wood_texture_does_not_hide_empty_bets_or_pot_prefix():
    frame=cv2.imread(str(Path(__file__).parent/'fixtures/wood_amounts_anonymous.png'))
    async def check():
        detector=TableDetector()
        for _ in range(3):result=await detector.detect(frame)
        assert result.pot==127366
        assert result.seat_bets=={0:0,1:0,2:0,3:0,4:0,5:60958,6:3000,7:60958}
        assert result.call_amount==60958
        assert result.reliable,result.reason
    asyncio.run(check())


def test_textured_empty_bet_rejects_digits_chips_and_gray_occlusion():
    from vision.table_detector import textured_empty_bet
    background=np.full((30,70,3),(60,110,160),np.uint8)
    assert textured_empty_bet(background,background)
    digit=background.copy()
    cv2.putText(digit,'1',(20,24),cv2.FONT_HERSHEY_SIMPLEX,.7,(220,220,220),1)
    assert not textured_empty_bet(digit,background)
    assert not textured_empty_bet(background,digit)
    assert not textured_empty_bet(np.full_like(background,40),background)


def test_sync_dealing_banner_is_separate_from_missing_amounts():
    label=cv2.imread(str(Path(__file__).parents[1]/'assets/sync_dealing_label.png'))
    frame=np.full((805,1152,3),35,np.uint8)
    frame[417:417+label.shape[0],494:494+label.shape[1]]=label
    detector=TableDetector()
    assert detector.sync_dealing(frame)
    assert detector.sync_dealing(cv2.resize(frame,(576,403)))
    assert not detector.sync_dealing(np.full_like(frame,35))
