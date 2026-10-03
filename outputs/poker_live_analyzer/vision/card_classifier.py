from dataclasses import dataclass
from pathlib import Path
import cv2
import numpy as np


@dataclass(frozen=True)
class RankResult:
    rank: str
    confidence: float
    margin: float


def normalize(mask):
    mask = np.uint8(mask > 0) * 255
    if np.count_nonzero(mask) < 8:
        return None
    x, y, width, height = cv2.boundingRect(mask)
    return np.uint8(cv2.resize(mask[y:y+height, x:x+width], (32, 56), interpolation=cv2.INTER_AREA) > 127)


class CardClassifier:
    """字形相似度辨識；分數是匹配指標，不是假定的模型機率。"""
    def __init__(self, path=None):
        from app_paths import resource_path
        path = Path(path) if path is not None else resource_path('models/rank_templates.npz')
        with np.load(path, allow_pickle=False) as data:
            self.labels = data['labels'].copy()
            self.masks = data['masks'].copy()
        self.areas = self.masks.sum(axis=(1, 2))
        self.groups = {rank: np.flatnonzero(self.labels == rank) for rank in '23456789TJQKA'}

    def example(self, rank):
        return self.masks[self.groups[rank][0]].copy()

    def classify(self, mask):
        target = normalize(mask)
        if target is None:
            return None
        intersections = (self.masks * target).sum(axis=(1, 2))
        scores = 2 * intersections / (self.areas + target.sum())
        ranks = sorted(((float(scores[indexes].max()), rank) for rank, indexes in self.groups.items()), reverse=True)
        score, rank = ranks[0]
        margin = score - ranks[1][0]
        if score < .85 or margin < .035:
            # 底牌略有傾斜時，以少量角度校正筆畫，仍要求同一匹配門檻。
            padded = np.pad(np.uint8(mask > 0)*255, 12)
            height, width = padded.shape
            best = {label: value for value, label in ranks}
            for angle in (-8, -4, 4, 8):
                rotated = cv2.warpAffine(padded, cv2.getRotationMatrix2D((width/2,height/2), angle, 1),
                    (width,height), flags=cv2.INTER_NEAREST)
                target = normalize(rotated)
                intersections = (self.masks*target).sum(axis=(1,2))
                scores = 2*intersections/(self.areas+target.sum())
                for label, indexes in self.groups.items():
                    best[label] = max(best[label], float(scores[indexes].max()))
            ranks = sorted((value,label) for label,value in best.items())
            score, rank = ranks[-1]
            margin = score-ranks[-2][0]
        if score < .85 or margin < .035:
            return None
        return RankResult(rank, score, margin)
