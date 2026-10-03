"""將可驗證的牌組畫成小圖，不使用猜測的對手真實底牌。"""
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QPixmap,QPainter,QColor,QFont

def hand_picture(hole,best):
    picture=QPixmap(440,92)
    picture.fill(QColor('#eff6f3'))
    painter=QPainter(picture)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QColor('#203b50'))
    painter.setFont(QFont('Noto Sans TC',10))
    painter.drawText(3,15,'對手底牌範例')
    painter.drawText(152,15,'可組成的五張牌')
    suits={'s':'♠','h':'♥','d':'♦','c':'♣'}
    for cards,start in ((hole,3),(best,152)):
        for index,card in enumerate(cards):
            x=start+index*55
            painter.setPen(QColor('#82939b'))
            painter.setBrush(QColor('white'))
            painter.drawRoundedRect(QRectF(x,23,48,65),5,5)
            painter.setPen(QColor('#c42b36' if card[1] in 'hd' else '#172d3c'))
            painter.setFont(QFont('Inter',16,QFont.Bold))
            painter.drawText(QRectF(x,25,48,30),Qt.AlignCenter,card[0].replace('T','10'))
            painter.drawText(QRectF(x,54,48,30),Qt.AlignCenter,suits[card[1]])
    painter.end()
    return picture
