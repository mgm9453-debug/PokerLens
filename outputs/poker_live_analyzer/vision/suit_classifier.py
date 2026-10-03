"""花色按字形確認；顏色只限制候選，不直接把黑色當黑桃。"""
from pathlib import Path
import numpy as np
import cv2
from .card_classifier import normalize


class SuitClassifier:
    def __init__(self):
        from app_paths import resource_path
        with np.load(resource_path('models/suit_templates.npz'), allow_pickle=False) as data:
            self.labels, self.masks = data['labels'].copy(), data['masks'].copy()
        # 上半部輪廓區分黑桃尖頂與梅花圓瓣；下半部兩者相似。
        self.weights = np.ones((56,32),dtype=np.uint8)
        self.weights[:28] = 5
        self.weighted_masks = self.masks*self.weights
        self.areas = self.weighted_masks.sum(axis=(1,2))

    def classify(self, mask, candidates='scdh'):
        target = normalize(mask)
        if target is None:
            return None
        scores = 2*(self.weighted_masks*target).sum(axis=(1,2))/(self.areas+(target*self.weights).sum())
        ranked = sorted((float(scores[self.labels==suit].max()), suit) for suit in candidates)
        score, suit = ranked[-1]
        margin = score-ranked[-2][0] if len(ranked)>1 else score
        if score<.90 or margin<.025:
            # 傾斜底牌會讓小花色的邊緣多出一兩格；校正後再比較候選字形。
            best={label:value for value,label in ranked}
            padded=np.pad(np.uint8(mask>0)*255,8)
            height,width=padded.shape
            for angle in (-8,-4,4,8):
                rotated=cv2.warpAffine(padded,cv2.getRotationMatrix2D((width/2,height/2),angle,1),(width,height),flags=cv2.INTER_NEAREST)
                target=normalize(rotated)
                scores=2*(self.weighted_masks*target).sum(axis=(1,2))/(self.areas+(target*self.weights).sum())
                for label in candidates:
                    best[label]=max(best[label],float(scores[self.labels==label].max()))
            ranked=sorted((value,label) for label,value in best.items())
            score,suit=ranked[-1]
            margin=score-ranked[-2][0] if len(ranked)>1 else score
        return (suit, score) if score>=.90 and margin>=.025 else None
