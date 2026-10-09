"""辨識目前八人桌的紅色與綠色牌背；未知座位不假定為持牌或棄牌。"""
from dataclasses import dataclass
import cv2
import numpy as np


@dataclass(frozen=True)
class PlayerDetection:
    active_seats: tuple[int, ...]
    reliable: bool
    reason: str = ''


# 原始實體視窗尺寸的牌背位置，使用比例換算以追蹤視窗縮放。
# 座位零由底牌辨識器確認，此處只處理七位對手。
SEAT_REGIONS = {
    1: (214/1128, 511/799, 60/1128, 55/799),
    2: (72/1128, 357/799, 60/1128, 55/799),
    3: (142/1128, 163/799, 60/1128, 55/799),
    4: (490/1128, 110/799, 60/1128, 55/799),
    5: (839/1128, 163/799, 60/1128, 55/799),
    6: (908/1128, 357/799, 60/1128, 55/799),
    7: (775/1128, 511/799, 60/1128, 55/799),
}

# 六人桌沿用同一座位編號；左右中間兩席不存在，不拿頭像填補。
SIX_SEAT_REGIONS = {
    1:(.160,.595,.053,.075),
    3:(.157,.233,.051,.073),
    4:(.441,.134,.052,.073),
    5:(.725,.233,.051,.073),
    7:(.725,.595,.051,.075),
}


class PlayerDetector:
    @property
    def seat_layout(self):
        return self._fixed_seat_layout or (6 if self._regions is SIX_SEAT_REGIONS else 8)

    def __init__(self,green_only=False,regions=None,seat_layout=None,exact_seats=()):
        if seat_layout not in (None,6,8):raise ValueError('尚未支援此座位配置')
        self.green_only=green_only
        self._fixed_seat_layout=seat_layout
        self._regions=regions if regions is not None else (SIX_SEAT_REGIONS if seat_layout==6 else SEAT_REGIONS)
        self._exact_seats=frozenset(exact_seats)
        from app_paths import resource_path
        path=resource_path('assets/card_back_emblem.png')
        self.emblem=cv2.imdecode(np.fromfile(path,dtype=np.uint8),cv2.IMREAD_GRAYSCALE) if path.is_file() else None

    def green_state(self,crop,height):
        hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
        green=(hsv[:,:,0]>35)&(hsv[:,:,0]<95)&(hsv[:,:,1]>45)&(hsv[:,:,2]>55)
        gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
        if gray.max()<8: return 'unknown'
        # 顏色只作候選篩選；牌背須同時具有圓形黑桃圖案。
        if self.emblem is not None and green.mean()>.08:
            for scale in (.65,.75,.9,1,1.1,1.25,1.4):
                size=round(self.emblem.shape[0]*height/799*scale)
                if size<10 or size>min(gray.shape): continue
                template=cv2.resize(self.emblem,(size,size))
                score=cv2.matchTemplate(gray,template,cv2.TM_CCOEFF_NORMED)
                _,maximum,_,position=cv2.minMaxLoc(score)
                x,y=position
                if maximum>=.72 and green[y:y+size,x:x+size].mean()>.45:
                    return 'active'
        if green.mean()<.15: return 'empty'
        # 平滑桌布沒有牌背圖案及亮色邊框；整張空白畫面已在入口拒絕。
        border=(hsv[:,:,1]<60)&(hsv[:,:,2]>185)
        edges=cv2.Canny(gray,60,120)
        if border.mean()<.005 and (edges>0).mean()<.08: return 'empty'
        # 零散文字不具有牌背面積與寬高；大片可疑物件仍保留待確認。
        mask=np.uint8(green)*255
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            _,_,w,h=cv2.boundingRect(contour)
            area=cv2.contourArea(contour)
            if w>=crop.shape[1]*.35 and h>=crop.shape[0]*.5 and area>=crop.shape[0]*crop.shape[1]*.18 and area/max(1,w*h)>.72:
                return 'unknown'
        return 'empty' if gray.std()>18 else 'unknown'


    def detect(self, frame):
        if frame is None or frame.ndim != 3 or frame.shape[2] != 3 or min(frame.shape[:2]) < 240:
            return PlayerDetection((), False, '牌桌尺寸不足，無法確認持牌人數')
        height, width = frame.shape[:2]
        if frame.max()<8 or float(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY).std())<2:
            return PlayerDetection((),False,'牌桌畫面為空白，等待新畫面')
        active = []
        regions=self._regions
        if self.green_only and self._fixed_seat_layout is None:
            # 至少兩個完整牌背圖案支持，且比八人配置更多，才切換配置。
            # 沒有牌或仍在動畫時不以頭像顏色猜測新配置。
            def support(candidate):
                count=0
                for x,y,w,h in candidate.values():
                    patch=frame[max(0,round((y-h*.12)*height)):round((y+h*1.18)*height),
                        max(0,round((x-w*.12)*width)):round((x+w*1.18)*width)]
                    count+=self.green_state(patch,height)=='active'
                return count
            six=support(SIX_SEAT_REGIONS)
            eight=support(SEAT_REGIONS)
            if six>=2 and six>eight:
                self._regions=SIX_SEAT_REGIONS
            elif eight>=2 and eight>six:
                self._regions=SEAT_REGIONS
            regions=self._regions
        for seat, region in regions.items():
            x, y, w, h = region
            crop = frame[round(y*height):round((y+h)*height), round(x*width):round((x+w)*width)]
            if crop.size == 0:
                return PlayerDetection((), False, f'座位 {seat} 畫面不完整')
            if self.green_only:
                # 容許牌背動畫或縮放造成少量位移，不把整個頭像當牌背。
                expanded=crop if seat in self._exact_seats else frame[max(0,round((y-h*.12)*height)):round((y+h*1.18)*height),
                    max(0,round((x-w*.12)*width)):round((x+w*1.18)*width)]
                state=self.green_state(expanded,height)
                if state=='active':
                    active.append(seat)
                    continue
                if state=='empty': continue
                return PlayerDetection((),False,f'座位 {seat} 牌背圖案不完整，正在重新確認')
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            red = ((hsv[:, :, 0] < 12) | (hsv[:, :, 0] > 165)) & (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 75)
            green = (hsv[:,:,0]>35) & (hsv[:,:,0]<95) & (hsv[:,:,1]>45) & (hsv[:,:,2]>55)
            back = green if self.green_only else red | green
            red_fraction = float(back.mean())
            if self.green_only and red_fraction<.15:
                if gray.max()<8:
                    return PlayerDetection((),False,f'座位 {seat} 畫面為黑色，等待新畫面')
                continue
            if red_fraction < .15:
                white = np.uint8((crop.min(axis=2)>185) & (crop.max(axis=2).astype(np.int16)-crop.min(axis=2)<40))*255
                white_contours,_ = cv2.findContours(white,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                for contour in white_contours:
                    _,_,cw,ch=cv2.boundingRect(contour)
                    area=cv2.contourArea(contour)
                    polygon=cv2.approxPolyDP(contour,.03*cv2.arcLength(contour,True),True)
                    if area>crop.shape[0]*crop.shape[1]*.35 and .5<cw/max(1,ch)<1.3 and area/(cw*ch)>.8 and len(polygon)==4:
                        return PlayerDetection((),False,f'座位 {seat} 出現攤牌或未知白色牌面，持牌狀態待確認')
            if red_fraction >= .55 and float(gray.std()) >= 8:
                mask = np.uint8(back) * 255
                mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3,3), np.uint8))
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                largest = max(contours, key=cv2.contourArea, default=None)
                if largest is not None:
                    _, _, cw, ch = cv2.boundingRect(largest)
                    area=cv2.contourArea(largest)
                    polygon=cv2.approxPolyDP(largest,.035*cv2.arcLength(largest,True),True)
                    rectangular=len(polygon)<=6 and area/max(1,cw*ch)>.70
                    if rectangular and cw >= crop.shape[1]*.65 and ch >= crop.shape[0]*.70 and area >= crop.shape[0]*crop.shape[1]*.45:
                        active.append(seat)
                        continue
            if self.green_only:
                return PlayerDetection((),False,f'座位 {seat} 綠色物件尚未確認為牌背，等待下一幀')
            # 空白或被遮蓋不等於棄牌；只接受低紅色且有清楚頭像紋理的無牌位置。
            clear_avatar = red_fraction < .15 and float(gray.std()) > 18 and float(gray.mean()) > 45 and float(np.percentile(gray, 80)) > 120
            if not clear_avatar and red_fraction < .15:
                # 牌背突出於頭像左側；不同頭像明暗差異大，另確認右側頭像紋理。
                ax = round((x+w*.65)*width)
                avatar = frame[round(y*height):round((y+h)*height), ax:round((x+w*1.9)*width)]
                if avatar.size:
                    avatar_gray = cv2.cvtColor(avatar, cv2.COLOR_BGR2GRAY)
                    clear_avatar = float(avatar_gray.std()) > 18 and float(np.percentile(avatar_gray,80)) > 70
            if not clear_avatar:
                return PlayerDetection((), False, f'座位 {seat} 牌背或頭像不清楚，等待下一幀')
        return PlayerDetection(tuple(active), True)
