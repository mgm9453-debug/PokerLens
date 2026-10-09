"""真正的新影格才能增加牌面、人數與金額確認次數。"""
from types import SimpleNamespace
import numpy as np
import pytest
import vision.worker as module
from vision.card_detector import Detection
from vision.player_detector import PlayerDetection
from vision.table_detector import TableAmounts


@pytest.mark.parametrize('timestamps,expected,table_count',[
    ([100.0,100.0,100.1,100.2],3,1),([100.0,100.0,100.0,100.0],1,0)])
def test_worker_skips_same_source_frame_before_any_detection(monkeypatch,timestamps,expected,table_count):
    reads=[];detections=[];money_calls=[];tables=[];fresh=[]
    class Capture:
        def __init__(self,*args,**kwargs):self._received=None
        def open(self):pass
        def read(self):
            self._received=timestamps[len(reads)]
            reads.append(self._received)
            return np.full((799,1128,3),90,np.uint8)
        def read_sample(self):return self.read(),self._received
        def close(self):pass
    class Cards:
        def detect(self,image):
            detections.append(True)
            return Detection(('As','Kd'),(),.95,True,hero_reliable=True,hero_confidence=.95,board_reliable=True)
    class Players:
        seat_layout=8
        def detect(self,image):return PlayerDetection((1,),True)
    class Money:
        ocr=SimpleNamespace(big_blind=None)
        def set_seat_layout(self,layout):pass
        async def detect(self,image):
            money_calls.append(True)
            return TableAmounts(1000,9000,0,{seat:0 for seat in range(8)},True,'',0,hero_turn=True)
        def reset(self):pass
    monkeypatch.setattr(module,'WindowCapture',Capture)
    monkeypatch.setattr(module,'build_detectors',lambda *args,**kwargs:(Cards(),Players(),Money()))
    monkeypatch.setattr(module.time,'monotonic',lambda:100.3)
    monkeypatch.setattr('capture.window_capture.list_tables',lambda:[])
    worker=module.VisionWorker(1);worker.refresh_ms=0
    monkeypatch.setattr(worker,'isInterruptionRequested',lambda:len(reads)>=len(timestamps))
    worker.table.connect(tables.append)
    worker.frame_received.connect(fresh.append)
    worker.run()
    assert len(detections)==len(money_calls)==expected
    assert len(tables)==table_count
    assert fresh==sorted(set(timestamps))


def test_slow_ocr_result_is_not_emitted_as_fresh_amounts(monkeypatch):
    now=[100.0];reads=[];amounts=[];tables=[];errors=[]
    class Capture:
        def __init__(self,*args,**kwargs):pass
        def open(self):pass
        def read_sample(self):
            reads.append(True)
            return np.full((799,1128,3),90,np.uint8),now[0]
        def close(self):pass
    class Cards:
        def detect(self,image):
            return Detection(('As','Kd'),(),.95,True,hero_reliable=True,hero_confidence=.95,board_reliable=True)
    class Players:
        seat_layout=8
        def detect(self,image):return PlayerDetection((1,),True)
    class Money:
        ocr=SimpleNamespace(big_blind=None)
        def set_seat_layout(self,layout):pass
        async def detect(self,image):
            now[0]+=3
            return TableAmounts(1000,9000,0,{seat:0 for seat in range(8)},True,'',0,hero_turn=True)
        def reset(self):pass
    monkeypatch.setattr(module,'WindowCapture',Capture)
    monkeypatch.setattr(module,'build_detectors',lambda *args,**kwargs:(Cards(),Players(),Money()))
    monkeypatch.setattr(module.time,'monotonic',lambda:now[0])
    monkeypatch.setattr('capture.window_capture.list_tables',lambda:[])
    worker=module.VisionWorker(1);worker.refresh_ms=0
    monkeypatch.setattr(worker,'isInterruptionRequested',lambda:len(reads)>=3)
    worker.amounts.connect(amounts.append);worker.table.connect(tables.append)
    worker.unavailable.connect(errors.append)
    worker.run()
    assert not amounts and not tables
    assert len(errors)==3 and all('逾期' in error for error in errors)
