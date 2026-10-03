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


class PlayerDetector:
    def __init__(self,green_only=False):
        self.green_only=green_only

    def detect(self, frame):
        if frame is None or frame.ndim != 3 or frame.shape[2] != 3 or min(frame.shape[:2]) < 240:
            return PlayerDetection((), False, '牌桌尺寸不足，無法確認持牌人數')
        height, width = frame.shape[:2]
        if frame.max()<8 or float(frame.std())<2:
            return PlayerDetection((),False,'牌桌畫面為空白，等待新畫面')
        active = []
        for seat, region in SEAT_REGIONS.items():
            x, y, w, h = region
            crop = frame[round(y*height):round((y+h)*height), round(x*width):round((x+w)*width)]
            if crop.size == 0:
                return PlayerDetection((), False, f'座位 {seat} 畫面不完整')
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
