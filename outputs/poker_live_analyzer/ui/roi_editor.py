from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QImage, QPainter, QColor, QPen
from PySide6.QtWidgets import QWidget
from capture.profiles import Region, TableProfile


class RoiEditor(QWidget):
    selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(600, 280)
        self.image = QImage()
        self.profile = TableProfile({})
        self.target = '牌桌'
        self.start = None
        self.end = None

    def image_rect(self):
        if self.image.isNull():
            return QRectF(self.rect())
        scale = min(self.width() / self.image.width(), self.height() / self.image.height())
        width, height = self.image.width() * scale, self.image.height() * scale
        return QRectF((self.width()-width)/2, (self.height()-height)/2, width, height)

    def set_frame(self, frame):
        height, width = frame.shape[:2]
        self.image = QImage(frame.data, width, height, frame.strides[0], QImage.Format.Format_BGR888).copy()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#12202c'))
        rect = self.image_rect()
        if self.image.isNull():
            painter.setPen(QColor('#bacbd6'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '選擇螢幕或虛擬攝影機來源，開始擷取\n拖曳畫面設定選定區域；此階段不自動辨識牌局')
        else:
            painter.drawImage(rect, self.image)
        painter.setPen(QPen(QColor('#46ddb0'), 2))
        for name, region in self.profile.regions.items():
            box = QRectF(rect.x()+region.x*rect.width(), rect.y()+region.y*rect.height(), region.width*rect.width(), region.height*rect.height())
            painter.drawRect(box)
            painter.drawText(box.topLeft(), name)
        if self.start is not None and self.end is not None:
            painter.drawRect(QRectF(self.start, self.end).normalized())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.image_rect().contains(event.position()):
            self.start = self.end = event.position()

    def mouseMoveEvent(self, event):
        if self.start is not None:
            rect = self.image_rect()
            point = event.position()
            point.setX(max(rect.left(), min(rect.right(), point.x())))
            point.setY(max(rect.top(), min(rect.bottom(), point.y())))
            self.end = point
            self.update()

    def mouseReleaseEvent(self, event):
        if self.start is None:
            return
        box = QRectF(self.start, self.end).normalized()
        rect = self.image_rect()
        if box.width() > 3 and box.height() > 3:
            self.profile.regions[self.target] = Region((box.x()-rect.x())/rect.width(), (box.y()-rect.y())/rect.height(), box.width()/rect.width(), box.height()/rect.height())
            self.selected.emit(self.target)
        self.start = self.end = None
        self.update()
