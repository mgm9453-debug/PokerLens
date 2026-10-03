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
