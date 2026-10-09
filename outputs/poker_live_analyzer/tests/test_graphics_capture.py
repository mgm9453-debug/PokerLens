"""視窗內容擷取：遮擋不阻擋，失效來源與過時影格不得沿用。"""
from types import SimpleNamespace
import numpy as np
import pytest

@pytest.fixture
def backend(monkeypatch):
    from capture import graphics_capture as module
    checks=[]
    monkeypatch.setattr(module,'_validated_rect',lambda handle,regions:(checks.append(regions) or (10,20,16,24)))
    monkeypatch.setattr(module,'_visible_rect',lambda handle:None)
    class Native:
        def __init__(self,**kwargs): self.options=kwargs;self.events={};self.stopped=False
        def event(self,callback): self.events[callback.__name__]=callback;return callback
        def start_free_threaded(self): return self
        def stop(self): self.stopped=True
        def is_finished(self): return self.stopped
        def emit(self,buffer,timestamp):
            self.events['on_frame_arrived'](SimpleNamespace(frame_buffer=buffer,timespan=timestamp),None)
    capture=module.GraphicsWindowCapture(123,native_factory=Native,read_timeout=.01)
    capture.open()
    return module,capture,checks

def pixels(): return np.full((4,6,4),[20,70,140,255],np.uint8)

def test_overlapping_windows_do_not_block_direct_window_capture(backend):
    module,capture,checks=backend
    image=pixels();capture._native.emit(image,1)
    image[:]=0
    result=capture.read()
    assert checks and all(regions==() for regions in checks)
    assert capture._native.options['window_hwnd']==123
    assert result.shape==(4,6,3)
    assert result[0,0].tolist()==[20,70,140]
    capture.close()

def test_old_native_timestamp_does_not_refresh_stale_image(backend,monkeypatch):
    module,capture,_=backend
    clock=[100.0];monkeypatch.setattr(module,'monotonic',lambda:clock[0])
    capture._native.emit(pixels(),10)
    clock[0]+=3
    capture._native.emit(pixels(),10)
    with pytest.raises(RuntimeError,match='停止更新'): capture.read()
    capture.close()

def test_black_frame_is_rejected(backend):
    module,capture,_=backend
    capture._native.emit(np.zeros((4,6,4),np.uint8),1)
    with pytest.raises(RuntimeError,match='黑畫面'): capture.read()
    capture.close()

def test_resize_waits_for_new_matching_frame(backend,monkeypatch):
    module,capture,_=backend
    capture._native.emit(pixels(),1)
    monkeypatch.setattr(module,'_validated_rect',lambda *args:(10,20,17,24))
    with pytest.raises(RuntimeError,match='尺寸'): capture.read()
    capture.close()

def test_visible_frame_is_padded_to_outer_window(backend,monkeypatch):
    module,capture,_=backend
    monkeypatch.setattr(module,'_validated_rect',lambda *args:(9,20,17,25))
    monkeypatch.setattr(module,'_visible_rect',lambda handle:(10,20,16,24))
    capture._native.emit(pixels(),1)
    result=capture.read()
    assert result.shape==(5,8,3)
    assert result[0,1].tolist()==[20,70,140]
    assert not result[:,0].any()
    capture.close()

def test_native_close_invalidates_latest_frame(backend):
    module,capture,_=backend
    capture._native.emit(pixels(),1)
    capture._native.events['on_closed']()
    with pytest.raises(RuntimeError,match='關閉'): capture.read()
    capture.close()

def test_late_callback_from_previous_session_is_ignored(backend):
    module,capture,_=backend
    callback=capture._native.events['on_frame_arrived']
    capture.close();capture.open()
    callback(SimpleNamespace(frame_buffer=pixels(),timespan=100),None)
    with pytest.raises(RuntimeError,match='等待'): capture.read()
    capture.close()


def test_atomic_sample_carries_source_time_and_does_not_refresh_on_read(backend,monkeypatch):
    module,capture,_=backend
    now=[100.0]
    monkeypatch.setattr(module,'monotonic',lambda:now[0])
    capture._native.emit(pixels(),1)
    image,received=capture.read_sample()
    assert received==100.0
    now[0]=100.5
    again,received_again=capture.read_sample()
    assert received_again==received
    assert np.array_equal(image,again)
    capture._native.emit(pixels(),2)
    _,received_new=capture.read_sample()
    assert received_new==100.5
    capture.close()
