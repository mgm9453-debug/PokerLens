from threading import Lock


class FrameBuffer:
    """保留最新影格，避免慢速消費者累积過時畫面。"""
    def __init__(self):
        self._frame = None
        self._lock = Lock()

    def put(self, frame):
        with self._lock:
            self._frame = frame

    def get(self):
        with self._lock:
            frame, self._frame = self._frame, None
            return frame
