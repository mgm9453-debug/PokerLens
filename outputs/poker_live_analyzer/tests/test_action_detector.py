"""實際行動按鈕與預選框分開，不把未知畫面當作自身回合。"""
import cv2
import numpy as np
from pathlib import Path


def frame(buttons=3):
    image=np.full((799,1128,3),60,np.uint8)
    for index in range(buttons):
        x=round((.62+.125*index)*1128)
        cv2.rectangle(image,(x,727),(x+125,782),(30,30,180),-1)
    return image


def test_three_live_buttons_confirm_turn_and_raise_access():
    from vision.action_detector import ActionDetector
    result=ActionDetector().detect(frame())
    assert result.hero_turn is True
    assert result.can_raise is True


def test_two_buttons_allow_call_but_do_not_invent_raise_access():
    from vision.action_detector import ActionDetector
    result=ActionDetector().detect(frame(2))
    assert result.hero_turn is True
    assert result.can_raise is False


def test_preselection_boxes_are_not_live_action_buttons():
    from vision.action_detector import ActionDetector
    image=frame(0)
    for index in range(3):
        cv2.rectangle(image,(700+index*120,741),(715+index*120,756),(220,220,220),1)
    assert ActionDetector().detect(image).hero_turn is False


def test_black_or_single_partial_button_is_unknown():
    from vision.action_detector import ActionDetector
    assert ActionDetector().detect(np.zeros((799,1128,3),np.uint8)).hero_turn is None
    assert ActionDetector().detect(frame(1)).hero_turn is None


def test_equal_scale_keeps_button_detection():
    from vision.action_detector import ActionDetector
    for size in [(564,400),(1692,1198)]:
        assert ActionDetector().detect(cv2.resize(frame(),size)).hero_turn is True


def test_actual_anonymous_wpt_buttons_confirm_turn():
    from vision.action_detector import ActionDetector
    image=cv2.imread(str(Path(__file__).parent/'fixtures/action_buttons_anonymous.png'))
    for factor in (1,.5,1.5):
        result=ActionDetector().detect(cv2.resize(image,None,fx=factor,fy=factor))
        assert result.hero_turn is True
        assert result.can_raise is True
