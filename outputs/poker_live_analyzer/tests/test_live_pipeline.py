"""用匿名真實畫面驗證背景辨識到介面更新，不操作遊戲。"""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys
import time
from pathlib import Path
import cv2
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest


@pytest.mark.skipif(sys.platform!='win32',reason='需要本機原生文字辨識')
@pytest.mark.parametrize('filename,hero,pot,call,opponents',[
    ('live_anonymous.png',['Ad','8d'],555,185,6),
    ('angled_allin_anonymous.png',['4s','5s'],9765,7415,4)])
def test_live_pipeline_needs_no_analysis_click(tmp_path,monkeypatch,filename,hero,pot,call,opponents):
    from ui.main_window import MainWindow
    from capture.window_capture import TableWindow
    frame=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures'/filename,np.uint8),1)
    # 舊匿名畫面使用紅牌背，僅將牌背區轉成目前指定的綠色。
    from vision.player_detector import SEAT_REGIONS
    h,w=frame.shape[:2]
    for x,y,rw,rh in SEAT_REGIONS.values():
        region=frame[round(y*h):round((y+rh)*h),round(x*w):round((x+rw)*w)]
        hsv=cv2.cvtColor(region,cv2.COLOR_BGR2HSV)
        red=((hsv[:,:,0]<12)|(hsv[:,:,0]>165))&(hsv[:,:,1]>70)&(hsv[:,:,2]>75)
        hsv[:,:,0][red]=60
        region[:]=cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR)
    class Capture:
        def __init__(self,*args,**kwargs): pass
        def open(self): pass
        def read(self): return frame.copy()
        def close(self): pass
    monkeypatch.setattr('vision.worker.WindowCapture',Capture)
    monkeypatch.setattr('ui.main_window.list_tables',lambda:[TableWindow(1,'盲注50/100',(0,0,1128,799))])
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.toggle_auto()
    try:
        for _ in range(400):
            app.processEvents()
            time.sleep(.02)
            if window.result: break
        assert window.result is not None,window.auto_status.text()
        assert window.result['live']
        assert window.detector.state.hero_cards==hero
        assert window.detector.state.pot==pot
        assert window.result['call_amount']==call
        assert window.result['opponents']==opponents
        assert '%' in window.analysis.win_label.text()
        assert '行動參考' in window.analysis.summary.text()
        assert '對手手牌範圍尚未從行動確認' in window.analysis.extra.text()
        saved=window.repository.get_analysis(window.detector.version)
        assert saved['live'] and saved['call_amount']==call
    finally:
        window.close()
