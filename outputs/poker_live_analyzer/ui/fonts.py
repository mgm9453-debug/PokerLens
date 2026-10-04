"""隨程式載入指定字體，以字形回退分配中文與英文數字。"""
from pathlib import Path
from PySide6.QtGui import QFont,QFontDatabase

_loaded=False

def interface_font():
    global _loaded
    if not _loaded:
        from app_paths import resource_path
        directory=resource_path('assets/fonts')
        for name in ('Inter.ttf','NotoSansTC.ttf','GenSenRounded-R.otf','GenSenRounded-M.otf'):
            if QFontDatabase.addApplicationFont(str(directory/name))<0:
                raise RuntimeError('無法載入介面字體：'+name)
        _loaded=True
    font=QFont()
    font.setFamilies(['Inter','Noto Sans TC','GenSenRounded2 TW'])
    font.setPointSize(11)
    return font
