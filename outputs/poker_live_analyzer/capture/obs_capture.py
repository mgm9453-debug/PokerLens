import cv2


class ObsCapture:
    """讀取已開啟的虛擬攝影機；攝影機編號由使用者選擇。"""
    def __init__(self, index=0):
        self.index = index
        self._source = None

    def open(self):
        self._source = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
        if not self._source.isOpened():
            self.close()
            raise ValueError('無法開啟攝影機，請先啟動虛擬攝影機並確認編號')

    def read(self):
        success, frame = self._source.read()
        if not success:
            raise RuntimeError('攝影機未提供影格')
        return frame

    def close(self):
        if self._source:
            self._source.release()
            self._source = None
