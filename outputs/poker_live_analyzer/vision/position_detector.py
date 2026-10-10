"""只從牌桌內圈的小圓形莊家徽章確認位置，不以頭像辨識。"""
import cv2
import numpy as np

ANCHORS = {0: (.57,.67), 1: (.32,.59), 2: (.22,.48), 3: (.32,.30),
    4: (.57,.30), 5: (.70,.30), 6: (.79,.48), 7: (.70,.59)}
SIX_ANCHORS = {0: (.57,.65), 1: (.32,.59), 3: (.31,.35),
    4: (.57,.29), 5: (.70,.35), 7: (.70,.59)}


class DealerDetector:
    def __init__(self, ocr):
        self.ocr = ocr
        from app_paths import resource_path
        path=resource_path('assets/dealer_badge.png')
        self.template=cv2.imdecode(np.fromfile(path,dtype=np.uint8),cv2.IMREAD_GRAYSCALE) if path.is_file() else None
        self.reset()

    def reset(self):
        self.previous = None
        self.count = 0

    async def detect(self, frame, layout=8):
        if frame is None or frame.ndim != 3 or min(frame.shape[:2]) < 240:
            self.reset()
            return None
        height, width = frame.shape[:2]
        anchors = SIX_ANCHORS if layout == 6 else ANCHORS
        candidates = []
        for seat, (ax, ay) in anchors.items():
            x0, x1 = round((ax-.07)*width), round((ax+.07)*width)
            y0, y1 = round((ay-.06)*height), round((ay+.06)*height)
            patch = frame[y0:y1, x0:x1]
            hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
            mask = np.uint8((hsv[:,:,1] < 85) & (hsv[:,:,2] > 165)) * 255
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                x,y,w,h = cv2.boundingRect(contour)
                area = cv2.contourArea(contour)
                perimeter = cv2.arcLength(contour, True)
                if not (.014*height <= h <= .040*height and .75 <= w/max(1,h) <= 1.3
                        and perimeter > 0 and 4*np.pi*area/perimeter**2 > .72):
                    continue
                cx,cy = (x0+x+w/2)/width, (y0+y+h/2)/height
                nearby = [s for s,(px,py) in anchors.items() if abs(cx-px)<.07 and abs(cy-py)<.06]
                if nearby != [seat]:
                    continue
                badge = patch[max(0,y-2):min(patch.shape[0],y+h+2), max(0,x-2):min(patch.shape[1],x+w+2)]
                matched=False
                if self.template is not None:
                    gray=cv2.cvtColor(badge,cv2.COLOR_BGR2GRAY)
                    for factor in (.9,1,1.1):
                        size=round(self.template.shape[0]*height/793*factor)
                        if 10<=size<=min(gray.shape):
                            sample=cv2.resize(self.template,(size,size))
                            if cv2.minMaxLoc(cv2.matchTemplate(gray,sample,cv2.TM_CCOEFF_NORMED))[1]>=.88:
                                matched=True
                                break
                if not matched and hasattr(self.ocr,'recognize'):
                    text = await self.ocr.recognize(cv2.resize(badge, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC))
                    matched=text.available and text.text.strip().upper() == 'D'
                if matched:
                    candidates.append(seat)
        # 同時有兩個徽章候選時不選其中一個，沒有徽章也不沿用舊候選。
        value = candidates[0] if len(candidates) == 1 else None
        self.count = self.count+1 if value is not None and self.previous == value else (1 if value is not None else 0)
        self.previous = value
        return value if self.count >= 2 else None
