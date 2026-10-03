"""使用造成實機停滯的匿名畫面，回歸三個已重現的辨識原因。"""
import asyncio
import sys
from pathlib import Path
import cv2
import numpy as np
import pytest
from vision.card_detector import CardDetector
from vision.player_detector import PlayerDetector
from vision.table_detector import TableDetector


def frame():
    return cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/angled_allin_anonymous.png',np.uint8),1)


def test_angled_spade_five_does_not_block_hero_cards():
    result=CardDetector().detect(frame())
    assert result.reliable
    assert result.hero==('4s','5s')


def test_small_spades_do_not_block_hero_or_board():
    image=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/small_spades_anonymous.png',np.uint8),1)
    result=CardDetector().detect(image)
    assert result.reliable
    assert result.hero==('Ts','6s')
    assert result.board==('Kd','Jd','9s')


def test_hero_confirmation_is_independent_of_incomplete_board():
    image=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/small_spades_anonymous.png',np.uint8),1)
    image[335:456,430:607]=0
    result=CardDetector().detect(image)
    assert not result.reliable
    assert result.hero_reliable
    assert result.hero==('Ts','6s')
    assert result.hero_confidence>=.85


def test_untrained_live_hearts_on_resized_table():
    image=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/縮小紅心底牌匿名.png',np.uint8),1)
    result=CardDetector().detect(image)
    assert result.reliable
    assert result.hero==('9h','8h')
    assert result.board==('As','2h','Qc')


def test_four_visible_board_cards_are_all_confirmed():
    image=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/四張公共牌匿名.png',np.uint8),1)
    result=CardDetector().detect(image)
    assert result.reliable
    assert result.hero==('4d','7d')
    assert result.board==('4h','9c','3s','Qs')


def test_red_table_rail_does_not_block_folded_seat():
    result=PlayerDetector().detect(frame())
    assert result.reliable,result.reason
    assert result.active_seats==(1,3,4,5)


@pytest.mark.skipif(sys.platform!='win32',reason='需要原生文字辨識')
def test_four_digit_left_bet_keeps_leading_digit():
    async def check():
        detector=TableDetector()
        for _ in range(3): result=await detector.detect(frame())
        assert result.reliable,result.reason
        assert result.seat_bets[1]==7915
        assert result.call_amount==7415
    asyncio.run(check())
