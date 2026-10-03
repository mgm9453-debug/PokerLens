"""金額觀測：原生辨識加連續多幀一致性，不捏造缺失值。"""
from dataclasses import dataclass,field
from time import perf_counter
import cv2
import numpy as np
from .ocr_engine import NativeOcrEngine

def normalized(x,y,w,h): return (x/1128,y/799,w/1128,h/799)
POT_ROI=normalized(495,292,165,45)
HERO_STACK_ROI=normalized(512,692,110,32)
CALL_ROI=normalized(875,741,79,32)
CALL_NUMBER_ROI=normalized(840,750,130,30)
BET_ROIS={0:normalized(533,531,54,37),1:normalized(338,507,98,35),2:normalized(224,430,51,39),3:normalized(270,313,68,44),4:normalized(534,256,68,38),5:normalized(798,313,68,44),6:normalized(838,423,68,44),7:normalized(719,507,45,39)}
CHIP_ROIS={s:(max(0,r[0]-.01),max(0,r[1]-28/799),min(r[2]+.02,1-max(0,r[0]-.01)),28/799) for s,r in BET_ROIS.items()}
STACK_ROIS={0:HERO_STACK_ROI,1:normalized(234,591,92,35),2:normalized(99,436,87,35),3:normalized(173,244,91,36),4:normalized(514,195,101,36),5:normalized(865,244,92,36),6:normalized(935,436,100,36),7:normalized(803,591,101,36)}

def crop(frame,roi):
    h,w=frame.shape[:2]
    x,y,rw,rh=roi
    return frame[int(y*h):int((y+rh)*h),int(x*w):int((x+rw)*w)]

def empty_bet_evidence(image):
    # 只檢查亮度變化與筆畫；桌布色相不參與下注判斷。
    # 黑畫面與有明顯物件的區域不能推論零下注。
    if not image.size: return False
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    return bool(15<float(gray.mean())<210 and gray.std()<12 and not cv2.Canny(gray,30,70).any())

def chip_evidence(image):
    if not image.size: return True
    # 籌碼的邊緣與紋理提供證據，不以桌布或籌碼顏色判定。
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    mask=cv2.Canny(gray,30,70)
    count,labels,stats,centroids=cv2.connectedComponentsWithStats(mask,8)
    return any(stat[cv2.CC_STAT_AREA]>=8
        and stat[cv2.CC_STAT_HEIGHT]>=image.shape[0]*.35
        and .5<stat[cv2.CC_STAT_WIDTH]/max(1,stat[cv2.CC_STAT_HEIGHT])<5
        and stat[cv2.CC_STAT_AREA]/max(1,stat[cv2.CC_STAT_WIDTH]*stat[cv2.CC_STAT_HEIGHT])>.22
        for stat in stats[1:])

@dataclass(frozen=True)
class TableAmounts:
    pot: float | None
    hero_stack: float | None
    call_amount: float | None
    seat_bets: dict[int,float]
    reliable: bool
    reason: str
    milliseconds: float
    seat_stacks: dict[int,float] = field(default_factory=dict)
    field_reliable: dict[str,bool] = field(default_factory=dict)
    paused: bool = False

class TableDetector:
    def __init__(self,stable_frames=3,ocr=None,pot_roi=POT_ROI,hero_stack_roi=HERO_STACK_ROI,call_roi=CALL_ROI,bet_rois=None,stack_rois=None,chip_rois=None):
        if stable_frames<2: raise ValueError('金額至少需要兩幀一致確認')
        self.ocr=ocr or NativeOcrEngine()
        self.stable_frames=stable_frames
        self.pot_roi=pot_roi; self.hero_stack_roi=hero_stack_roi; self.call_roi=call_roi
        self.bet_rois=BET_ROIS if bet_rois is None else bet_rois
        self.stack_rois=STACK_ROIS if stack_rois is None else stack_rois
        self.chip_rois=CHIP_ROIS if chip_rois is None else chip_rois
        for roi in [pot_roi,hero_stack_roi,call_roi,*self.bet_rois.values(),*self.stack_rois.values(),*self.chip_rois.values()]:
            if len(roi)!=4 or any(not np.isfinite(v) or v<0 for v in roi) or roi[0]+roi[2]>1 or roi[1]+roi[3]>1 or min(roi[2:])<=0: raise ValueError('辨識區域須為有效正規化座標')
        self.previous={}; self.counts={}

    def reset(self): self.previous.clear(); self.counts.clear()

    def stable(self,key,value):
        if value is None:
            self.previous.pop(key,None); self.counts[key]=0
            return False
        self.counts[key]=self.counts.get(key,0)+1 if self.previous.get(key)==value else 1
        self.previous[key]=value
        return self.counts[key]>=self.stable_frames

    async def detect(self,frame):
        started=perf_counter()
        if frame is None or not isinstance(frame,np.ndarray) or frame.ndim!=3 or frame.shape[2]!=3 or not frame.size:
            self.reset()
            return TableAmounts(None,None,None,{},False,'缺少有效牌桌影格',(perf_counter()-started)*1000)
        values={}
        for key,roi in [('pot',self.pot_roi),('hero_stack',self.hero_stack_roi),('call_amount',self.call_roi)]:
            values[key]=await self.ocr.read_amount(crop(frame,roi))
        if values['call_amount'] is None and self.call_roi==CALL_ROI:
            values['call_amount']=await self.ocr.read_amount(crop(frame,CALL_NUMBER_ROI))
        bets={}; stacks={}
        for seat,roi in self.bet_rois.items():
            region=crop(frame,roi)
            value=await self.ocr.read_amount(region)
            chip_roi=self.chip_rois.get(seat)
            no_chip=chip_roi is not None and not chip_evidence(crop(frame,chip_roi))
            if value is None and no_chip and empty_bet_evidence(region): value=0.0
            values[f'bet_{seat}']=value
            if value is not None: bets[seat]=value
        for seat,roi in self.stack_rois.items():
            value=values['hero_stack'] if seat==0 else await self.ocr.read_amount(crop(frame,roi))
            values[f'stack_{seat}']=value
            if value is not None: stacks[seat]=value
        # 按鈕未顯示數字時，只從全部已讀下注與自身籌碼推導跟注差額。
        # 空白按鈕本身不提供任何零金額證據。
        if values['call_amount'] is None and values['hero_stack'] is not None and set(bets)==set(range(8)):
            values['call_amount']=min(values['hero_stack'],max(0,max(bets.values())-bets[0]))
        reliable_fields={key:self.stable(key,value) for key,value in values.items()}
        missing=[key for key in ('pot','hero_stack','call_amount') if values[key] is None]
        core_stable=all(reliable_fields[key] for key in ('pot','hero_stack','call_amount'))
        bets_stable=all(reliable_fields[f'bet_{seat}'] for seat in self.bet_rois)
        consistent=values['pot'] is not None and values['pot']+1e-9>=sum(bets.values()) and values['hero_stack'] is not None and values['call_amount'] is not None and values['call_amount']<=values['hero_stack']
        reliable=core_stable and bets_stable and consistent
        missing_bets=[str(s) for s in self.bet_rois if values[f'bet_{s}'] is None]
        reason='缺少必要金額，等待辨識：'+ '、'.join({'pot':'底池','hero_stack':'自身籌碼','call_amount':'跟注額'}[key] for key in missing) if missing else '無法確認下注額或空下注區的座位：'+ '、'.join(missing_bets) if missing_bets else '金額不一致，拒絕更新' if not consistent else '等待連續多幀金額一致' if not reliable else ''
        if not missing and not missing_bets and not consistent:
            reason=(f'金額不一致：底池 {values["pot"]:,.0f}、桌上下注合計 {sum(bets.values()):,.0f}'
                if values['pot']+1e-9<sum(bets.values()) else
                f'金額不一致：跟注 {values["call_amount"]:,.0f}、自己剩餘籌碼 {values["hero_stack"]:,.0f}')
        paused=False
        if values['pot'] is None and hasattr(self.ocr,'recognize'):
            text=await self.ocr.recognize(crop(frame,normalized(440,350,230,140)))
            paused=text.available and 'onbreak' in ''.join(text.text.lower().split())
            if paused: reason='牌局休息中，恢復發牌後自動更新'
        return TableAmounts(values['pot'],values['hero_stack'],values['call_amount'],bets,reliable,reason,(perf_counter()-started)*1000,stacks,reliable_fields,paused)
