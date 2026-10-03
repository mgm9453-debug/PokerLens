from PySide6.QtCore import QThread, Signal
from capture.frame_buffer import FrameBuffer


class CaptureWorker(QThread):
    error = Signal(str)

    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.source = source
        self.buffer = FrameBuffer()

    def run(self):
        try:
            self.source.open()
            while not self.isInterruptionRequested():
                self.buffer.put(self.source.read())
                self.msleep(33)
        except Exception as error:
            self.error.emit(str(error))
        finally:
            self.source.close()
