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
    """黑曜石底紋與金屬框；紋理只在閱讀區外側繪製。"""
    def paintEvent(self,event):
        super().paintEvent(event)
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        rect=QRectF(self.rect()).adjusted(4,4,-4,-4)
        background=QLinearGradient(rect.topLeft(),rect.bottomRight())
        background.setColorAt(0,QColor('#17140e'));background.setColorAt(.25,QColor('#070809'))
        background.setColorAt(.8,QColor('#090909'));background.setColorAt(1,QColor('#211a0f'))
        painter.setBrush(background);painter.setPen(Qt.NoPen);painter.drawRoundedRect(rect,20,20)
        painter.save()
        clip=QPainterPath();clip.addRoundedRect(rect,20,20);painter.setClipPath(clip)
        for index in range(24):
            x=(index*137+29)%max(1,self.width());y=(index*83)%max(1,self.height())
            vein=QPainterPath();vein.moveTo(x,y)
            for step in range(8):
                x+=((index*19+step*31)%41)-20;y+=24+(step*13)%32
                vein.lineTo(x,y)
                if step%3==0:
                    vein.lineTo(x+19,y+10);vein.moveTo(x,y)
            painter.setPen(QPen(QColor(178,141,75,28 if index%3 else 65),.7));painter.drawPath(vein)
        painter.restore()
        # 固定的細緻石紋，不隨資料更新或重繪改變。
        for side in (0,1):
            for index in range(28):
                x=7+(index*13)%22 if side==0 else self.width()-7-(index*13)%22
                y=(index*113)%max(1,self.height())
                vein=QPainterPath();vein.moveTo(x,y)
                vein.cubicTo(x+7,y+38,x-6,y+65,x+3,y+110)
                painter.setPen(QPen(QColor(199,158,81,65),.7));painter.drawPath(vein)
        metal=QLinearGradient(rect.topLeft(),rect.bottomRight())
        for point,color in ((0,'#735831'),(.18,'#f3d48e'),(.45,'#58452a'),(.75,'#b38b49'),(1,'#edd09a')):
            metal.setColorAt(point,QColor(color))
        painter.setBrush(Qt.NoBrush);painter.setPen(QPen(metal,1.4));painter.drawRoundedRect(rect,20,20)
        painter.setPen(QPen(QColor(216,174,98,40),1))
        painter.drawRoundedRect(rect.adjusted(3,3,-3,-3),17,17)
        painter.end()


class DecisionCard(QWidget):
    """共同決策卡片，只承載原有顯示元件。"""
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        rect=QRectF(self.rect()).adjusted(1,1,-1,-1)
        gradient=QLinearGradient(rect.topLeft(),rect.bottomRight())
        gradient.setColorAt(0,QColor('#1e1c17'));gradient.setColorAt(.35,QColor('#090909'));gradient.setColorAt(1,QColor('#171611'))
        metal=QLinearGradient(rect.topLeft(),rect.bottomRight())
        for stop,color in ((0,'#ffe5a4'),(.2,'#987435'),(.5,'#ffe2a0'),(.8,'#82602c'),(1,'#efc875')):metal.setColorAt(stop,QColor(color))
        painter.setBrush(gradient);painter.setPen(QPen(metal,1.5));painter.drawRoundedRect(rect,18,18)
        painter.end()
