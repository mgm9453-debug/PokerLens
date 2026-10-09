"""由 WPT 底部實際紅色行動按鈕確認自身回合，預選框不算。"""
from dataclasses import dataclass
import cv2
import numpy as np


@dataclass(frozen=True)
class ActionObservation:
    hero_turn: bool | None
    can_raise: bool | None = None


class ActionDetector:
    def detect(self,frame):
        if frame is None or frame.ndim!=3 or frame.shape[2]!=3 or min(frame.shape[:2])<240:
            return ActionObservation(None)
        height,width=frame.shape[:2]
        region=frame[round(height*.86):,round(width*.60):]
        if not region.size or region.max()<15:
            return ActionObservation(None)
        hsv=cv2.cvtColor(region,cv2.COLOR_BGR2HSV)
        red=(((hsv[:,:,0]<14)|(hsv[:,:,0]>165))&(hsv[:,:,1]>90)&(hsv[:,:,2]>75)).astype(np.uint8)*255
        kernel=max(2,round(height*.004))
        red=cv2.morphologyEx(red,cv2.MORPH_CLOSE,np.ones((kernel,kernel),np.uint8))
        count,_,stats,_=cv2.connectedComponentsWithStats(red,8)
        boxes=[]
        for x,y,w,h,area in stats[1:]:
            if (w>=region.shape[1]*.15 and h>=region.shape[0]*.20
                    and 1.3<w/max(1,h)<5 and area/(w*h)>.60):
                boxes.append((x,y,w,h))
        if len(boxes) in (2,3):
            boxes.sort()
            centers=[y+h/2 for x,y,w,h in boxes]
            if max(centers)-min(centers)<=region.shape[0]*.12:
                return ActionObservation(True,len(boxes)==3)
        if boxes:
            return ActionObservation(None)
        return ActionObservation(False,False)
