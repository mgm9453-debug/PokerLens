"""直接擷取指定視窗的圖形內容，避免桌面遮擋與過時影格。"""
from threading import Condition
from time import monotonic
import numpy as np
from .window_capture import _validated_rect, _physical_coordinates


def _visible_rect(handle):
    import ctypes
    from ctypes import wintypes
    try:
        with _physical_coordinates():
            rect=wintypes.RECT()
            result=ctypes.windll.dwmapi.DwmGetWindowAttribute(
                wintypes.HWND(handle),9,ctypes.byref(rect),ctypes.sizeof(rect))
            if result==0:
                return rect.left,rect.top,rect.right,rect.bottom
    except (OSError,RuntimeError):
        pass
    return None


class GraphicsWindowCapture:
    def __init__(self,handle,protected_regions=None,native_factory=None,max_age=2.0,read_timeout=1.0):
        self.handle=int(handle)
        self._factory=native_factory
        self.max_age=max_age
        self.read_timeout=read_timeout
        self._condition=Condition()
        self._native=None
        self._control=None
        self._generation=0
        self._latest=None
        self._received=0.0
        self._native_timestamp=None
        self._closed=False
        self._error=''

    def open(self):
        self.close()
        # 視窗內容來源不依賴桌面遮擋；仍檢查程式身分、存在與最小化。
        _validated_rect(self.handle,())
        try:
            factory=self._factory
            if factory is None:
                from windows_capture import WindowsCapture
                factory=WindowsCapture
            native=factory(window_hwnd=self.handle,cursor_capture=None,draw_border=None)
            with self._condition:
                token=self._generation
                self._native=native
                self._closed=False
                self._error=''

            @native.event
            def on_frame_arrived(frame,control):
                try:
                    timestamp=frame.timespan
                    now=monotonic()
                    with self._condition:
                        if token!=self._generation or self._closed: return
                        if self._native_timestamp is not None and timestamp<=self._native_timestamp: return
                        self._native_timestamp=timestamp
                        # 本機來源可超過百幀，只複製約每秒十二幀以控制成本。
                        if self._latest is not None and now-self._received<.08: return
                        pixels=frame.frame_buffer
                        if pixels.ndim!=3 or pixels.shape[2]<3 or pixels.dtype!=np.uint8 or not pixels.size:
                            self._latest=None;self._error='視窗內容影格格式無效'
                        else:
                            image=pixels[:,:,:3].copy()
                            if image.max()<8 or int(image.max())-int(image.min())<2:
                                self._latest=None;self._error='視窗內容為黑畫面或空白，暫停辨識'
                            else:
                                self._latest=image;self._received=now;self._error=''
                        self._condition.notify_all()
                except Exception:
                    with self._condition:
                        if token==self._generation:
                            self._latest=None;self._error='無法讀取視窗內容影格'
                            self._condition.notify_all()

            @native.event
            def on_closed():
                with self._condition:
                    if token==self._generation:
                        self._closed=True;self._latest=None
                        self._condition.notify_all()

            self._control=native.start_free_threaded()
        except Exception as error:
            self.close()
            raise RuntimeError('無法啟動視窗內容擷取，請確認視窗已開啟及系統支援') from error

    def read(self):
        if self._control is None: raise RuntimeError('視窗內容擷取尚未開啟')
        rect=_validated_rect(self.handle,())
        deadline=monotonic()+self.read_timeout
        with self._condition:
            while self._latest is None and not self._closed and not self._error:
                remaining=deadline-monotonic()
                if remaining<=0: break
                self._condition.wait(remaining)
            if self._closed: raise RuntimeError('視窗內容來源已關閉')
            if self._error: raise RuntimeError(self._error)
            if self._latest is None: raise RuntimeError('等待視窗內容的新影格')
            if monotonic()-self._received>self.max_age:
                raise RuntimeError('視窗內容停止更新，暫停使用舊影格')
            image=self._latest.copy()
        if self._control.is_finished(): raise RuntimeError('視窗內容擷取已停止')
        if image.shape[:2]!=(rect[3]-rect[1],rect[2]-rect[0]):
            visible=_visible_rect(self.handle)
            if (visible is None or image.shape[:2]!=(visible[3]-visible[1],visible[2]-visible[0])
                    or _validated_rect(self.handle,())!=rect
                    or not (rect[0]<=visible[0]<visible[2]<=rect[2]
                            and rect[1]<=visible[1]<visible[3]<=rect[3])):
                raise RuntimeError('視窗尺寸正在變動，等待新尺寸影格')
            # 補回系統隱形邊框，維持既有辨識區域的座標比例，不拉伸牌面。
            padded=np.zeros((rect[3]-rect[1],rect[2]-rect[0],3),dtype=np.uint8)
            x,y=visible[0]-rect[0],visible[1]-rect[1]
            padded[y:y+image.shape[0],x:x+image.shape[1]]=image
            image=padded
        return image

    def read_sample(self):
        """原子讀取影像與來源接收時間；反覆讀取不冒充新的影格。"""
        with self._condition:
            image=self.read()
            return image,self._received

    def close(self):
        with self._condition:
            self._generation+=1
            control=self._control
            self._control=None;self._native=None;self._latest=None
            self._received=0.0;self._native_timestamp=None
            self._closed=False;self._error=''
            self._condition.notify_all()
        if control is not None:
            try: control.stop()
            except Exception: pass
