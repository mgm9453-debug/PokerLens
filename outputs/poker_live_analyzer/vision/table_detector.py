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

def six_normalized(x,y,w,h): return x/1146,y/772,w/1146,h/772
SIX_BET_ROIS={s:six_normalized(*r) for s,r in {
    0:(540,510,75,36),1:(315,468,110,38),3:(270,330,85,36),
    4:(535,238,90,36),5:(758,330,85,36),7:(750,472,88,36)}.items()}
SIX_STACK_ROIS={0:HERO_STACK_ROI,**{s:six_normalized(*r) for s,r in {
    1:(205,540,100,33),3:(200,260,102,28),4:(528,187,94,30),
    5:(847,261,94,30),7:(849,540,100,33)}.items()}}
SIX_CHIP_ROIS={s:(r[0],max(0,r[1]-30/772),r[2],30/772) for s,r in SIX_BET_ROIS.items()}

def crop(frame,roi):
    h,w=frame.shape[:2]
    x,y,rw,rh=roi
    return frame[int(y*h):int((y+rh)*h),int(x*w):int((x+rw)*w)]

def empty_bet_evidence(image):
    # 只檢查亮度變化與筆畫；桌布色相不參與下注判斷。
    # 黑畫面與有明顯物件的區域不能推論零下注。
    if not image.size: return False
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    height,width=gray.shape
    margin=max(1,round(width*.1))
    interior=gray[:,margin:-margin] if width>2*margin else gray
    if not (15<float(interior.mean())<210 and interior.std()<12):return False
    edges=cv2.Canny(gray,30,70)
    _,_,stats,_=cv2.connectedComponentsWithStats(edges,8)
    noise=0
    for x,y,w,h,area in stats[1:]:
        # 頭像輪廓可能擦過區域側邊；只能忽略貼邊且細長的輪廓。
        border=(x==0 or x+w==width) and w<=max(2,width*.08) and h>=height*.7
        if border:continue
        # 桌布的孤立細點不能當成數字；真正的筆畫仍拒絕推論為零。
        if w>max(2,np.ceil(width*.1)) or h>max(2,np.ceil(height*.1)):return False
        noise+=area
    return noise<=gray.size*.01

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


def textured_empty_bet(region,chips):
    # 彩色紋理不是下注：區域須保持有色背景，且數字區與籌碼區都無亮色中性筆畫。
    # 灰黑遮擋、低對比未知畫面及任何可能的數字／籌碼，均不推論零。
    for image in (region,chips):
        if image is None or not image.size:return False
        pixels=image.astype(np.int16)
        neutral=(pixels.max(axis=2)-pixels.min(axis=2)<55)&(pixels.min(axis=2)>140)
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        if gray.mean()<40 or gray.mean()>210:return False
        if np.median(pixels.max(axis=2)-pixels.min(axis=2))<55:return False
        count,_,stats,_=cv2.connectedComponentsWithStats(neutral.astype(np.uint8),8)
        if any(s[cv2.CC_STAT_AREA]>=3 for s in stats[1:]):return False
    return True

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
    bb_display: bool = False
    all_in_seats: tuple[int,...] = ()
    seats: tuple[int,...] = tuple(range(8))
    core_reliable: bool = False
    hero_turn: bool | None = None
    can_raise: bool | None = None
    amount_unit: str = '籌碼'
    amount_resolution: dict[str,float] = field(default_factory=dict)

class TableDetector:
    def __init__(self,stable_frames=3,ocr=None,pot_roi=POT_ROI,hero_stack_roi=HERO_STACK_ROI,call_roi=CALL_ROI,bet_rois=None,stack_rois=None,chip_rois=None,big_blind=None,seat_layout=None,exact_fields=()):
        if stable_frames<2: raise ValueError('金額至少需要兩幀一致確認')
        if seat_layout not in (None,6,8):raise ValueError('尚未支援此座位配置')
        self.ocr=ocr or NativeOcrEngine(big_blind=big_blind)
        self.stable_frames=stable_frames
        self.pot_roi=pot_roi; self.hero_stack_roi=hero_stack_roi; self.call_roi=call_roi
        self.bet_rois=BET_ROIS if bet_rois is None else bet_rois
        self.stack_rois=STACK_ROIS if stack_rois is None else stack_rois
        self.chip_rois=CHIP_ROIS if chip_rois is None else chip_rois
        for roi in [pot_roi,hero_stack_roi,call_roi,*self.bet_rois.values(),*self.stack_rois.values(),*self.chip_rois.values()]:
            if len(roi)!=4 or any(not np.isfinite(v) or v<0 for v in roi) or roi[0]+roi[2]>1 or roi[1]+roi[3]>1 or min(roi[2:])<=0: raise ValueError('辨識區域須為有效正規化座標')
        self.previous={}; self.counts={}
        from .action_detector import ActionDetector
        self.action_detector=ActionDetector()
        self._seat_layout=seat_layout or 8
        self._fixed_seat_layout=seat_layout
        self._exact_fields=frozenset(exact_fields)
        self._original_regions=(self.bet_rois,self.stack_rois,self.chip_rois)
        from app_paths import resource_path
        path=resource_path('assets/sync_dealing_label.png')
        self._sync_label=cv2.imdecode(np.fromfile(path,dtype=np.uint8),cv2.IMREAD_GRAYSCALE) if path.is_file() else None

    def sync_dealing(self,frame):
        if self._sync_label is None:return False
        region=cv2.cvtColor(crop(frame,(.30,.35,.40,.30)),cv2.COLOR_BGR2GRAY)
        for factor in (.9,1,1.1):
            scale=frame.shape[0]/805*factor
            template=cv2.resize(self._sync_label,None,fx=scale,fy=scale)
            if min(template.shape)<8 or template.shape[0]>region.shape[0] or template.shape[1]>region.shape[1]:continue
            if cv2.minMaxLoc(cv2.matchTemplate(region,template,cv2.TM_CCOEFF_NORMED))[1]>=.88:return True
        return False

    def set_seat_layout(self,layout):
        if layout not in (6,8):raise ValueError('尚未支援此座位配置')
        if self._fixed_seat_layout is not None:return
        if layout==self._seat_layout:return
        self.bet_rois,self.stack_rois,self.chip_rois=(SIX_BET_ROIS,SIX_STACK_ROIS,SIX_CHIP_ROIS) if layout==6 else self._original_regions
        self._seat_layout=layout
        self.reset()

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
        from poker.amount_units import rounding_budget, format_amount
        unit=getattr(self.ocr,'amount_unit','籌碼')
        resolutions={}
        values={}
        if hasattr(self.ocr,'bb_display'): self.ocr.bb_display=False
        for key,roi in [('pot',self.pot_roi),('hero_stack',self.hero_stack_roi),('call_amount',self.call_roi)]:
            reader=self.ocr.read_pot_amount if key=='pot' and hasattr(self.ocr,'read_pot_amount') else self.ocr.read_amount
            values[key]=await reader(crop(frame,roi))
            resolutions[key]=getattr(self.ocr,'last_resolution',0)
        if values['pot'] is None and 'pot' not in self._exact_fields and hasattr(self.ocr,'locate_pot'):
            values['pot']=await self.ocr.locate_pot(crop(frame,(.25,.18,.5,.42)))
            resolutions['pot']=getattr(self.ocr,'last_resolution',0)
        if values['call_amount'] is None and self.call_roi==CALL_ROI and 'call_amount' not in self._exact_fields:
            values['call_amount']=await self.ocr.read_amount(crop(frame,CALL_NUMBER_ROI))
            resolutions['call_amount']=getattr(self.ocr,'last_resolution',0)
        if values['call_amount'] is None and 'call_amount' in self._exact_fields and hasattr(self.ocr,'recognize'):
            text=await self.ocr.recognize(cv2.resize(crop(frame,self.call_roi),None,fx=3,fy=3,interpolation=cv2.INTER_CUBIC))
            label=''.join(text.text.lower().split()) if text.available else ''
            if label in ('過牌','过牌','check'):values['call_amount']=0.0
        button_missing=values['call_amount'] is None
        bets={}; stacks={}; all_in=[]
        for seat,roi in self.bet_rois.items():
            region=crop(frame,roi)
            value=await self.ocr.read_amount(region)
            resolution=getattr(self.ocr,'last_resolution',0)
            if isinstance(self.ocr,NativeOcrEngine) and f'bet_{seat}' not in self._exact_fields:
                gray=cv2.cvtColor(region,cv2.COLOR_BGR2GRAY)
                edge=max(1,round(gray.shape[1]*.06))
                middle=gray[round(gray.shape[0]*.2):round(gray.shape[0]*.85)]
                threshold=max(100,float(np.median(gray))+40)
                clipped=bool((middle[:,:edge]>threshold).any() or (middle[:,-edge:]>threshold).any())
                if value is None or clipped:
                    # 只有筆畫貼邊或讀不到時才向左右擴大，避免加入旁邊的裝飾。
                    x,y,width,height=roi
                    left=max(0,x-.025)
                    wider=(left,y,min(width+.055,1-left),height)
                    complete=await self.ocr.read_amount(crop(frame,wider))
                    if complete is not None:
                        value=complete
                        resolution=getattr(self.ocr,'last_resolution',0)
            chip_roi=self.chip_rois.get(seat)
            no_chip=chip_roi is not None and not chip_evidence(crop(frame,chip_roi))
            if no_chip and f'chips_{seat}' in self._exact_fields:
                chip_region=crop(frame,chip_roi)
                no_chip=empty_bet_evidence(chip_region) or textured_empty_bet(chip_region,chip_region)
            if value is None and no_chip and empty_bet_evidence(region): value=0.0; resolution=0
            if value is None and chip_roi is not None and textured_empty_bet(region,crop(frame,chip_roi)):
                value=0.0
                resolution=0
            resolutions[f'bet_{seat}']=resolution if value is not None else 0
            values[f'bet_{seat}']=value
            if value is not None: bets[seat]=value
        for seat,roi in self.stack_rois.items():
            value=values['hero_stack'] if seat==0 else await self.ocr.read_amount(crop(frame,roi))
            if value is None and seat!=0 and hasattr(self.ocr,'recognize'):
                text=await self.ocr.recognize(cv2.resize(crop(frame,roi),None,fx=3,fy=3,interpolation=cv2.INTER_CUBIC))
                label=''.join(text.text.lower().split()) if text.available else ''
                if label in ('allin','all-in','全下'):
                    value=0.0
                    all_in.append(seat)
            resolutions[f'stack_{seat}']=resolutions.get('hero_stack',0) if seat==0 else getattr(self.ocr,'last_resolution',0) if value else 0
            values[f'stack_{seat}']=value
            if value is not None: stacks[seat]=value
        # 按鈕未顯示數字時，只從全部已讀下注與自身籌碼推導跟注差額。
        # 空白按鈕本身不提供任何零金額證據。
        if (values['call_amount'] is None and 'call_amount' not in self._exact_fields
                and values['hero_stack'] is not None and set(bets)==set(self.bet_rois)):
            values['call_amount']=min(values['hero_stack'],max(0,max(bets.values())-bets[0]))
            highest_seat=max(bets,key=bets.get)
            resolutions['call_amount']=(resolutions.get('hero_stack',0) if values['call_amount']==values['hero_stack'] else resolutions.get(f'bet_{highest_seat}',0)+resolutions.get('bet_0',0)) if unit=='BB' else 0
        elif (values['call_amount'] is not None and values['hero_stack'] is not None and set(bets)==set(self.bet_rois)
                and isinstance(self.ocr,NativeOcrEngine)):
            expected=min(values['hero_stack'],max(0,max(bets.values())-bets[0]))
            highest_seat=max(bets,key=bets.get)
            tolerance=rounding_budget(unit,resolutions,'call_amount','hero_stack') if expected==values['hero_stack'] else rounding_budget(unit,resolutions,'call_amount','bet_0',f'bet_{highest_seat}')
            if abs(values['call_amount']-expected)>tolerance:
                # 不直接把小數點改成千分位；重新讀筆畫並與獨立下注差額核對。
                for roi in ([self.call_roi,CALL_NUMBER_ROI] if self.call_roi==CALL_ROI and 'call_amount' not in self._exact_fields else [self.call_roi]):
                    confirmed=await self.ocr.read_amount_matching(crop(frame,roi),expected)
                    if confirmed is not None:
                        values['call_amount']=confirmed
                        resolutions['call_amount']=getattr(self.ocr,'last_resolution',0)
                        break
        reliable_fields={key:self.stable(key,value) for key,value in values.items()}
        missing=[key for key in ('pot','hero_stack','call_amount') if values[key] is None]
        core_stable=all(reliable_fields[key] for key in ('pot','hero_stack','call_amount'))
        bets_stable=all(reliable_fields[f'bet_{seat}'] for seat in self.bet_rois)
        # 尚未確認的單幀讀值不能否定可靠底池；確認後的下注仍提供一致性下限。
        confirmed_total=sum(value for seat,value in bets.items() if reliable_fields.get(f'bet_{seat}',False))
        pot_tolerance=rounding_budget(unit,resolutions,'pot',*[f'bet_{seat}' for seat in bets if reliable_fields.get(f'bet_{seat}',False)]) if unit=='BB' else 1e-9
        consistent=values['pot'] is not None and values['pot']+pot_tolerance>=confirmed_total and values['hero_stack'] is not None and values['call_amount'] is not None and values['call_amount']<=values['hero_stack']
        reliable=core_stable and bets_stable and consistent
        missing_bets=[str(s) for s in self.bet_rois if values[f'bet_{s}'] is None]
        reason='缺少必要金額，等待辨識：'+ '、'.join({'pot':'底池','hero_stack':'自身大盲數','call_amount':'跟注額'}[key] for key in missing) if missing else '無法確認下注額或空下注區的座位：'+ '、'.join(missing_bets) if missing_bets else '金額不一致，拒絕更新' if not consistent else '等待連續多幀金額一致' if not reliable else ''
        if not missing and not missing_bets and not consistent:
            reason=(f'金額不一致：底池 {format_amount(values["pot"],unit)}、桌上下注合計 {format_amount(sum(bets.values()),unit)}'
                if values['pot']+1e-9<sum(bets.values()) else
                f'金額不一致：跟注 {format_amount(values["call_amount"],unit)}、自己剩餘大盲數 {format_amount(values["hero_stack"],unit)}')
        if unit=='BB' and isinstance(self.ocr,NativeOcrEngine) and not self.ocr.bb_display:
            reliable=False
            core_stable=False
            reason='尚未確認大盲數顯示，請將牌桌金額切換為大盲數顯示'
        paused=False
        if button_missing and self.sync_dealing(frame):
            paused=True
            reliable=False
            reason='牌桌同步發牌中，發牌完成後自動更新；目前不提供下注建議'
        elif button_missing and isinstance(self.ocr,NativeOcrEngine):
            text=await self.ocr.recognize(cv2.resize(crop(frame,(.30,.35,.40,.30)),None,fx=2,fy=2))
            phase=''.join(text.text.split()) if text.available else ''
            if '同步發牌' in phase or '同步发牌' in phase:
                paused=True
                reliable=False
                reason='牌桌同步發牌中，發牌完成後自動更新；目前不提供下注建議'
        if values['pot'] is None and hasattr(self.ocr,'recognize'):
            text=await self.ocr.recognize(crop(frame,normalized(440,350,230,140)))
            on_break=text.available and 'onbreak' in ''.join(text.text.lower().split())
            paused=paused or on_break
            if on_break: reason='牌局休息中，恢復發牌後自動更新'
        action=self.action_detector.detect(frame)
        turn_stable=self.stable('hero_turn',action.hero_turn)
        raise_stable=self.stable('can_raise',action.can_raise)
        hero_turn=action.hero_turn if turn_stable else None
        return TableAmounts(values['pot'],values['hero_stack'],values['call_amount'],bets,reliable,reason,(perf_counter()-started)*1000,stacks,reliable_fields,paused,getattr(self.ocr,'bb_display',False),tuple(seat for seat in all_in if reliable_fields.get(f'stack_{seat}',False)),tuple(sorted(self.bet_rois)),
            core_stable and consistent and not paused,hero_turn,action.can_raise if hero_turn is True and raise_stable else None,unit,resolutions)
