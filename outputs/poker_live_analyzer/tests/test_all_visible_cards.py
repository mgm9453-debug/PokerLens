"""五十二牌留出尺寸及角度的完整兩張底牌辨識，含拒絕案例。"""
import numpy as np
import cv2
import pytest
from card_rendering import load_faces,render_pair
from vision.card_detector import CardDetector

@pytest.fixture(scope='module')
def faces(): return load_faces()

@pytest.fixture(scope='module')
def detector(): return CardDetector()

@pytest.mark.parametrize('card',[r+s for r in '23456789TJQKA' for s in 'cdhs'])
@pytest.mark.parametrize('width,angle,blur,offset',[(75,-5,False,0),(79,3,False,1),(83,7,False,-1),(87,-11,True,2)])
def test_all_cards_in_complete_hero_pair(card,width,angle,blur,offset,faces,detector):
    other='Ad' if card!='Ad' else 'Ks'
    result=detector.detect(render_pair(card,other,faces,width,angle,blur,offset))
    assert result.reliable,(card,result)
    assert result.hero==(card,other)

@pytest.mark.parametrize('card',['Ts','4c','Ah','Kd'])
def test_duplicate_cards_are_never_confirmed(card,faces,detector):
    assert not detector.detect(render_pair(card,card,faces)).reliable

@pytest.mark.parametrize('card',[r+s for r in '23456789TJQKA' for s in 'cdhs'])
@pytest.mark.parametrize('scale',[.82,.70])
def test_all_cards_when_whole_table_is_resized(card,scale,faces,detector):
    other='Ad' if card!='Ad' else 'Ks'
    frame=render_pair(card,other,faces,width=81,angle=-6)
    image=cv2.resize(frame,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA)
    result=detector.detect(image)
    assert result.reliable,(card,result)
    assert result.hero==(card,other)

def test_white_cards_without_glyphs_are_not_confirmed(detector):
    frame=np.zeros((799,1128,3),np.uint8)
    frame[582:665,510:627]=240
    assert not detector.detect(frame).reliable
