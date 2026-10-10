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
    # 使用真實綠色牌背圖樣，不能只把舊紅牌背染綠就視為同一圖樣。
    from vision.player_detector import SEAT_REGIONS,PlayerDetector
    occupied=PlayerDetector().detect(frame).active_seats
    sample=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/green_backs_anonymous.png',np.uint8),1)
    sx,sy,sw,sh=SEAT_REGIONS[2]
    back=sample[round(sy*799):round((sy+sh)*799),round(sx*1128):round((sx+sw)*1128)]
    h,w=frame.shape[:2]
    for seat in occupied:
        x,y,rw,rh=SEAT_REGIONS[seat]
        region=frame[round(y*h):round((y+rh)*h),round(x*w):round((x+rw)*w)]
        region[:]=cv2.resize(back,(region.shape[1],region.shape[0]))
    class Capture:
        def __init__(self,*args,**kwargs): pass
        def open(self): pass
        def read(self): return frame.copy()
        def close(self): pass
    from vision.ocr_engine import NativeOcrEngine
    from vision.calibrated_detection import build_detectors
    class BbFixtureReader(NativeOcrEngine):
        def parse_value(self,text):
            # 匿名舊樣本是籌碼畫面；只在測試中按已知盲注轉成大盲數來源。
            value=super().parse_value(text)
            if value is not None:
                self.bb_display=True
                self.last_resolution/=100
                return value/100
            return None
    def detectors(profile):
        return build_detectors(profile,ocr=BbFixtureReader())
    monkeypatch.setattr('vision.worker.build_detectors',detectors)
    pot/=100;call/=100
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
        assert window.result['amount_unit']=='BB' and window.detector.state.big_blind==1
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
