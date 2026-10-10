import asyncio
from types import SimpleNamespace
import cv2
import numpy as np
from vision.position_detector import DealerDetector


class BadgeOcr:
    async def recognize(self, image):
        return SimpleNamespace(available=True, text='D')


def frame(points):
    image = np.full((800, 1128, 3), (70, 45, 25), np.uint8)
    for x, y in points:
        center = (round(x * 1128), round(y * 800))
        cv2.circle(image, center, 10, (225, 225, 225), -1)
        cv2.putText(image, 'D', (center[0]-5, center[1]+5), cv2.FONT_HERSHEY_SIMPLEX, .4, (20,20,20), 1)
    return image


def test_only_one_confirmed_badge_and_no_avatar_guess():
    detector = DealerDetector(BadgeOcr())
    image = frame([(.7, .59)])
    assert asyncio.run(detector.detect(image, 8)) is None
    assert asyncio.run(detector.detect(image, 8)) == 7
    assert asyncio.run(detector.detect(frame([]), 8)) is None
    assert asyncio.run(detector.detect(frame([(.7,.59),(.32,.59)]), 8)) is None
    assert asyncio.run(detector.detect(frame([(.12,.15)]), 8)) is None


def test_non_badge_text_never_identifies_dealer():
    class WrongOcr:
        async def recognize(self, image):
            return SimpleNamespace(available=True, text='8')
    detector = DealerDetector(WrongOcr())
    for _ in range(3):
        assert asyncio.run(detector.detect(frame([(.7,.59)]), 8)) is None


def test_real_badge_template_without_ocr_survives_scaling():
    from app_paths import resource_path
    badge=cv2.imdecode(np.fromfile(resource_path('assets/dealer_badge.png'),dtype=np.uint8),cv2.IMREAD_COLOR)
    original=frame([])
    original[462:482,780:800]=badge
    for factor in (.75,1,1.3):
        image=cv2.resize(original,None,fx=factor,fy=factor)
        detector=DealerDetector(None)
        assert asyncio.run(detector.detect(image)) is None
        assert asyncio.run(detector.detect(image)) == 7
