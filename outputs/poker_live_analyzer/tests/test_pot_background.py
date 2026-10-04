import asyncio
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
import cv2
import numpy as np
import pytest
from vision.ocr_engine import parse_amount,NativeOcrEngine


def test_big_blind_amount_needs_known_conversion():
    assert parse_amount('3.5BB',big_blind=1200)==4200
    assert parse_amount('0.5 BB',big_blind=1200)==600
    assert parse_amount('14.3BB',big_blind=1200)==17160
    assert parse_amount('3.5BB') is None
    assert parse_amount('3.53B',big_blind=1200) is None
    assert parse_amount('3.5BB 6BB',big_blind=1200) is None
    assert parse_amount('17,825',big_blind=1200)==17825


def test_blinds_from_table_title():
    from vision.ocr_engine import blinds_from_title
    assert blinds_from_title('神秘賞金 - 盲注 600/1200')==(600,1200)
    assert blinds_from_title('Blind 50/100')==(50,100)
    assert blinds_from_title('保底 12,500') is None


def test_pot_rejects_multiple_distinct_candidates():
    from vision.ocr_engine import unique_amount
    assert unique_amount(['底池 100','100'])==100
    assert unique_amount(['100','200']) is None


@pytest.mark.skipif(__import__('sys').platform!='win32',reason='需要原生辨識')
@pytest.mark.parametrize('texture',[False,True])
def test_yellow_pot_on_plain_and_textured_background(texture):
    rng=np.random.default_rng(42)
    image=np.full((55,220,3),(75,95,115),np.uint8)
    if texture:
        image=np.clip(image.astype(float)+rng.normal(0,18,image.shape),0,255).astype(np.uint8)
    cv2.putText(image,'3.5BB',(65,35),cv2.FONT_HERSHEY_SIMPLEX,.8,(0,215,245),2,cv2.LINE_AA)
    assert asyncio.run(NativeOcrEngine(big_blind=1200).read_pot_amount(image))==4200


def test_bb_notice_is_independent_of_complete_amounts(tmp_path):
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow
    from vision.table_detector import TableAmounts
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.auto_active=True
    window.accept_auto_amounts(window.auto_generation,
        TableAmounts(None,None,None,{},False,'等待',1,bb_display=True))
    assert '請切換成籌碼顯示' in window.amount_unit_notice.text()
    assert not window.amount_unit_notice.isHidden()
    window.accept_auto_amounts(window.auto_generation,
        TableAmounts(None,None,None,{},False,'等待',1))
    assert window.amount_unit_notice.isHidden()
    window.close()


@pytest.mark.skipif(__import__('sys').platform!='win32',reason='需要原生辨識')
@pytest.mark.parametrize('background',[(35,35,35),(45,95,45),(150,75,30),(70,30,95),(90,120,150)])
def test_chip_amount_on_different_table_colors(background):
    image=np.full((55,190,3),background,np.uint8)
    cv2.putText(image,'4,200',(12,37),cv2.FONT_HERSHEY_SIMPLEX,.9,(235,235,235),2,cv2.LINE_AA)
    assert asyncio.run(NativeOcrEngine().read_amount(image))==4200


def test_unknown_amount_is_never_guessed_from_texture():
    rng=np.random.default_rng(12)
    image=rng.integers(20,180,(55,190,3),dtype=np.uint8)
    assert asyncio.run(NativeOcrEngine().read_pot_amount(image)) is None
