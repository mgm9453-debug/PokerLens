"""以靜態牌面生成留出條件，驗證整段底牌擷取而非直接比對模板。"""
from pathlib import Path
import cv2
import numpy as np

def load_faces():
    with np.load(Path(__file__).resolve().parents[1]/'models/visible_card_faces.npz',allow_pickle=False) as data:
        return dict(zip(data['labels'].tolist(),data['faces']))

def render_pair(first,second,faces,width=79,angle=-5,blur=False,offset=0):
    frame=np.zeros((799,1128,3),np.uint8)
    frame[:]=(160,93,43)
    for index,label in enumerate((first,second)):
        source=faces[label]
        height=round(source.shape[0]*width/source.shape[1])
        face=cv2.resize(source,(width,height),interpolation=cv2.INTER_CUBIC)
        padded=cv2.copyMakeBorder(face,16,16,16,16,cv2.BORDER_CONSTANT,value=(0,0,0,0))
        h,w=padded.shape[:2]
        rotated=cv2.warpAffine(padded,cv2.getRotationMatrix2D((w/2,h/2),angle if index==0 else -angle/2,1),(w,h),flags=cv2.INTER_CUBIC)
        x=488+index*53+offset;y=565
        alpha=rotated[:,:,3:4].astype(np.float32)/255
        region=frame[y:y+h,x:x+w]
        region[:]=np.clip(rotated[:,:,:3]*alpha+region*(1-alpha),0,255).astype(np.uint8)
    # 玩家名稱面板會遮住牌的下段，但保留點數與小花色。
    frame[668:733,482:641]=20
    if blur: frame=cv2.GaussianBlur(frame,(3,3),.45)
    return frame
