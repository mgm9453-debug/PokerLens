"""參考圖的裝飾繪製；資料、文字值與事件均由原元件保留。"""
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QPainter,QPainterPath,QColor,QLinearGradient,QPen,QFont
from PySide6.QtWidgets import QLabel,QWidget,QStyledItemDelegate,QStyle

class ReferenceLabel(QLabel):
    def __init__(self,text='',kind=None):
        super().__init__(text)
        self.kind=kind

    @staticmethod
    def rounded_path(rect):
        path=QPainterPath();path.addRoundedRect(rect,15,15);return path

    def paintEvent(self,event):
        if self.kind not in ('action','win','tie'):
            return super().paintEvent(event)
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        rect=QRectF(self.rect()).adjusted(.5,.5,-.5,-.5)
        painter.setClipPath(self.rounded_path(rect))
        gradient=QLinearGradient(rect.topLeft(),rect.bottomRight())
        gradient.setColorAt(0,QColor('#242322'));gradient.setColorAt(.45,QColor('#0D0F10'));gradient.setColorAt(1,QColor('#17191B'))
        painter.setBrush(gradient);painter.setPen(QPen(QColor('#66523A' if self.kind!='tie' else '#5D496C'),1));painter.drawRoundedRect(rect,15,15)
        path=QPainterPath()
        if self.kind=='action':
            path.moveTo(0,self.height()*.74);path.cubicTo(self.width()*.25,self.height()*1.3,self.width()*.80,self.height()*1.3,self.width(),8)
        else:
            path.moveTo(0,self.height()*.60);path.cubicTo(self.width()*.33,self.height()*1.18,self.width()*.65,self.height()*1.13,self.width(),self.height()*.50)
        color=QColor('#EAC272' if self.kind!='tie' else '#B38BCE')
        for width,alpha in ((12,8),(7,14),(3,24),(1,150)):
            color.setAlpha(alpha);painter.setPen(QPen(color,width));painter.setBrush(Qt.NoBrush);painter.drawPath(path)
        if self.kind in ('win','tie'):
            text=self.text();title='勝率' if self.kind=='win' else '平手'
            value=text.removeprefix(title).strip()
            font=QFont(self.font());font.setPixelSize(18);font.setWeight(QFont.Medium)
            painter.setFont(font);painter.setPen(QColor('#FFFFFF'));painter.drawText(QRectF(0,10,self.width(),28),Qt.AlignCenter,title)
            font.setPixelSize(self.font().pixelSize() if self.font().pixelSize()>0 else 32);font.setWeight(QFont.DemiBold)
            painter.setFont(font);painter.setPen(self.palette().windowText().color());painter.drawText(QRectF(0,37,self.width(),self.height()-41),Qt.AlignCenter,value)
            painter.end();return
        if self.kind=='action':
            area=QPainterPath();area.moveTo(self.width()*.75,0);area.lineTo(self.width(),0);area.lineTo(self.width(),self.height()*.70)
            area.cubicTo(self.width()*.90,self.height()*.25,self.width()*.84,self.height()*.12,self.width()*.75,0)
            sheen=QLinearGradient(self.width(),0,self.width()*.75,self.height()*.55)
            sheen.setColorAt(0,QColor(242,196,106,135));sheen.setColorAt(1,QColor(242,196,106,0))
            painter.setBrush(sheen);painter.setPen(Qt.NoPen);painter.drawPath(area)
        if self.kind=='action':
            # 細緻金色曲面與散點，置於文字外側。
            painter.setPen(QPen(QColor(238,194,108,28),.5))
            for offset in range(0,18,2):
                line=QPainterPath();line.moveTo(0,self.height()*.77+offset)
                line.cubicTo(self.width()*.25,self.height()*1.25+offset,self.width()*.80,self.height()*1.24+offset,self.width(),offset*.6)
                painter.drawPath(line)
            painter.setPen(QColor(238,194,108,45))
            for point in range(240):
                x=self.width()*.82+((point*31)%max(1,int(self.width()*.18)))
                y=(point*17)%max(1,int(self.height()*.34))
                painter.drawPoint(int(x),int(y))
        painter.end();super().paintEvent(event)

class RoundedCellDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        painter.save();painter.setRenderHint(QPainter.Antialiasing)
        rect=QRectF(option.rect).adjusted(1,1,-1,-1)
        painter.setPen(Qt.NoPen);painter.setBrush(index.data(Qt.BackgroundRole));painter.drawRoundedRect(rect,4,4)
        segments=index.data(Qt.UserRole+1)
        if segments:
            path=QPainterPath();path.addRoundedRect(rect,4,4)
            painter.save();painter.setClipPath(path)
            left=rect.left()
            for color,fraction in segments:
                width=rect.width()*fraction
                painter.fillRect(QRectF(left,rect.top(),width,rect.height()),QColor(color))
                left+=width
            painter.restore()
        if index.data(Qt.UserRole+2):
            painter.setPen(QPen(QColor('#f1ce7b'),2));painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1,1,-1,-1),4,4)
        painter.setFont(option.font);painter.setPen(index.data(Qt.ForegroundRole).color())
        painter.drawText(rect,Qt.AlignCenter,str(index.data(Qt.DisplayRole)));painter.restore()


class ReferenceSurface(QWidget):
    def paintEvent(self,event):
        super().paintEvent(event)
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(Qt.NoBrush);painter.setPen(QPen(QColor('#625035'),1))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(4,4,-4,-4),17,17)
        for y in (104,self.height()-24):
            path=QPainterPath();path.moveTo(5,y)
            path.cubicTo(self.width()*.24,y-42,self.width()*.28,y+10,self.width()*.48,y+3)
            gradient=QLinearGradient(0,y,self.width()*.5,y);gradient.setColorAt(0,QColor('#E7BE72'));gradient.setColorAt(1,QColor(231,190,114,0))
            painter.setPen(QPen(gradient,1.4));painter.drawPath(path)
        painter.end()
