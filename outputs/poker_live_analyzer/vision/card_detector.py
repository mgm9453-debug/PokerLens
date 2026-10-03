from dataclasses import dataclass
from time import perf_counter
import cv2
import numpy as np
from vision.card_classifier import CardClassifier
from vision.suit_classifier import SuitClassifier

HERO_REGION = (.40, .68, .22, .20)
BOARD_REGION = (.27, .35, .46, .24)


@dataclass(frozen=True)
class Detection:
    hero: tuple[str, ...]
    board: tuple[str, ...]
    confidence: float
    reliable: bool
    milliseconds: float = 0
    reason: str = ''
    hero_reliable: bool = False
    hero_confidence: float = 0.0
    board_reliable: bool = False

    def __post_init__(self):
        if self.reliable:
            cards = self.hero + self.board
            if len(set(cards)) != len(cards):
                raise ValueError('辨識牌面重複')
            if len(self.hero) not in (0, 2) or len(self.board) not in (0, 3, 4, 5):
                raise ValueError('辨識牌面張數不完整')


class StableCards:
    def __init__(self, frames=3):
        self.frames = frames
        self.key = None
        self.count = 0
        self.last_emitted = None

    def reset(self):
        self.key = None
        self.count = 0
        self.last_emitted = None

    def update(self, detection):
        if not detection.reliable or detection.confidence < .85:
            self.key = None
            self.count = 0
            return None
        key = (detection.hero, detection.board)
        self.count = self.count + 1 if key == self.key else 1
        self.key = key
        if self.count >= self.frames and key != self.last_emitted:
            self.last_emitted = key
            return detection
        return None


def crop_region(frame, region):
    height, width = frame.shape[:2]
    x, y, w, h = region
    return frame[int(y*height):int((y+h)*height), int(x*width):int((x+w)*width)]


class CardDetector:
    def __init__(self, hero_region=HERO_REGION, board_region=BOARD_REGION):
        self.classifier = CardClassifier()
        self.suit_classifier = SuitClassifier()
        self.hero_region, self.board_region = hero_region, board_region

    def detect(self, frame):
        started = perf_counter()
        hero, hero_scores, hero_uncertain = self.find_cards(crop_region(frame, self.hero_region))
        board, board_scores, board_uncertain = self.find_cards(crop_region(frame, self.board_region))
        cards = hero + board
        reliable = len(hero) in (0, 2) and len(board) in (0, 3, 4, 5) and len(set(cards)) == len(cards)
        if hero_uncertain or board_uncertain:
            reliable = False
        scores = hero_scores + board_scores
        confidence = min(scores) if scores else (1.0 if reliable else 0.0)
        reason = '' if reliable else '牌面不完整或匹配不足，等待下一幀'
        hero_reliable = not hero_uncertain and len(hero) in (0,2) and len(set(hero))==len(hero)
        board_reliable = not board_uncertain and len(board) in (0,3,4,5) and len(set(board))==len(board)
        hero_confidence = min(hero_scores) if hero_scores else (1.0 if hero_reliable else 0.0)
        return Detection(tuple(hero), tuple(board), confidence, reliable, (perf_counter()-started)*1000, reason,hero_reliable,hero_confidence,board_reliable)

    def find_cards(self, crop):
        if crop.size == 0:
            return [], [], False
        height = crop.shape[0]
        channels = crop.astype(np.int16)
        white = np.uint8((channels.min(axis=2) > 185) & (channels.max(axis=2)-channels.min(axis=2) < 65)) * 255
        white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        found = []
        uncertain = False
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if h < height*.28 or w < h*.20 or cv2.contourArea(contour) < h*h*.16:
                continue
            region = crop[y:y+h, x:x+w]
            inside = np.zeros((h, w), np.uint8)
            cv2.drawContours(inside, [contour-np.array([[[x,y]]])], -1, 255, -1)
            hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
            dark = region.max(axis=2) < 125
            colored = (hsv[:,:,1] > 95) & (hsv[:,:,2] < 240)
            ink = np.uint8((dark | colored) & (inside > 0))*255
            _, _, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
            components = [(int(cx),int(cy),int(cw),int(ch),int(area)) for cx,cy,cw,ch,area in stats[1:] if area >= 5]
            ranks = sorted([c for c in components if h*.24 <= c[3] <= h*.62 and c[1] < h*.28], key=lambda c:c[0])
            joined = []
            for component in ranks:
                if joined:
                    px,py,pw,ph,pa = joined[-1]
                    cx,cy,cw,ch,area = component
                    # 傾斜的十點數仍是兩個筆畫，但外接矩形可能輕微重疊。
                    if -min(pw,cw)*.5 <= cx-(px+pw) < h*.12 and abs(cy-py) < h*.08 and abs(ch-ph) < h*.15:
                        joined[-1] = (px,min(py,cy),cx+cw-px,max(py+ph,cy+ch)-min(py,cy),pa+area)
                        continue
                joined.append(component)
            count_before = len(found)
            for rx,ry,rw,rh,_ in joined:
                suits = [c for c in components if h*.10 <= c[3] <= h*.34 and
                         0 <= c[1]-(ry+rh) < h*.32 and abs(c[0]+c[2]/2-(rx+rw/2)) < h*.22]
                if not suits:
                    continue
                match = self.classifier.classify(ink[ry:ry+rh, rx:rx+rw])
                if match is None:
                    uncertain = True
                    continue
                sx,sy,sw,sh,_ = min(suits, key=lambda c: abs(c[0]+c[2]/2-(rx+rw/2)))
                symbol_hsv = hsv[sy:sy+sh, sx:sx+sw]
                symbol_ink = ink[sy:sy+sh, sx:sx+sw] > 0
                saturated = (symbol_hsv[:,:,1] > 95) & symbol_ink
                suit_score = 1.0
                if saturated.sum() > symbol_ink.sum()*.65:
                    hue = float(np.median(symbol_hsv[:,:,0][saturated]))
                    suit = 'd' if 90 <= hue <= 135 else 'c' if 30 <= hue < 90 else None
                    if hue < 15 or hue > 165:
                        shape = self.suit_classifier.classify(symbol_ink, 'hd')
                        suit = shape[0] if shape else None
                        suit_score = shape[1] if shape else 0
                else:
                    shape = self.suit_classifier.classify(symbol_ink, 'sc')
                    suit = shape[0] if shape else None
                    suit_score = shape[1] if shape else 0
                if suit:
                    found.append((x+rx, match.rank+suit, min(match.confidence,suit_score)))
                else:
                    uncertain = True
            if len(found) == count_before:
                uncertain = True
        found.sort(key=lambda item:item[0])
        return [item[1] for item in found], [item[2] for item in found], uncertain
