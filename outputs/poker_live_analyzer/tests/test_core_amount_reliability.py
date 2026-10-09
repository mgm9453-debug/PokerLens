import asyncio
import numpy as np
from vision.table_detector import TableDetector,crop,POT_ROI,HERO_STACK_ROI,CALL_ROI,BET_ROIS,CHIP_ROIS


def test_missing_unrelated_bet_does_not_destroy_core_amount_reliability():
    class Ocr:
        async def read_amount(self,image):
            return {100:9000,125:300,150:1500}.get(int(image[0,0,0]))
    image=np.full((799,1128,3),90,np.uint8)
    for roi,value in [(POT_ROI,150),(HERO_STACK_ROI,100),(CALL_ROI,125)]:
        crop(image,roi)[:]=value
    crop(image,BET_ROIS[1])[:]=0
    crop(image,CHIP_ROIS[1])[:]=0
    detector=TableDetector(ocr=Ocr())
    for _ in range(3):result=asyncio.run(detector.detect(image))
    assert result.core_reliable
    assert not result.reliable
    assert result.field_reliable['call_amount']
    assert not result.field_reliable['bet_1']


def test_single_unconfirmed_bet_spike_does_not_block_confirmed_core():
    class Ocr:
        async def read_amount(self,image):
            return {100:9000,125:300,150:1500,180:99999}.get(int(image[0,0,0]))
    image=np.full((799,1128,3),90,np.uint8)
    for roi,value in [(POT_ROI,150),(HERO_STACK_ROI,100),(CALL_ROI,125)]:
        crop(image,roi)[:]=value
    crop(image,BET_ROIS[1])[:]=0
    crop(image,CHIP_ROIS[1])[:]=0
    detector=TableDetector(ocr=Ocr())
    for _ in range(3):result=asyncio.run(detector.detect(image))
    assert result.core_reliable
    crop(image,BET_ROIS[1])[:]=180
    result=asyncio.run(detector.detect(image))
    assert not result.field_reliable['bet_1']
    assert result.core_reliable
    # 確認後的矛盾仍必須拒絕，不能一律忽略下注總額。
    for _ in range(2):result=asyncio.run(detector.detect(image))
    assert result.field_reliable['bet_1']
    assert not result.core_reliable
