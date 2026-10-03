import mss
import numpy as np


class ScreenCapture:
    def __init__(self, monitor=1):
        self.monitor = monitor
        self._source = None

    def open(self):
        self._source = mss.mss()
        if not 0 <= self.monitor < len(self._source.monitors):
            self.close()
            raise ValueError('找不到指定螢幕')

    def read(self):
        return np.asarray(self._source.grab(self._source.monitors[self.monitor]))[:, :, :3].copy()

    def close(self):
        if self._source:
            self._source.close()
            self._source = None
