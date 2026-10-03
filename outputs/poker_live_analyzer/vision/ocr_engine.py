"""僅使用本機視窗作業系統的原生文字辨識，不傳送畫面。"""
import re
import unicodedata
from dataclasses import dataclass
import cv2
import numpy as np

@dataclass(frozen=True)
class OcrText:
    text: str
    available: bool
    reason: str = ''

def parse_amount(text):
    text=unicodedata.normalize('NFKC',text).strip()
    if '-' in text or re.search(r'\d[A-Za-z]\d',text): return None
    numbers=re.findall(r'(?<![\w.])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w.,])',text)
    if len(numbers)!=1: return None
    value=float(numbers[0].replace(',',''))
    return value if np.isfinite(value) and 0<=value<=1e12 else None

class NativeOcrEngine:
    def __init__(self,language='en-US'):
        self.engine=None
        self.reason=''
        try:
            from winrt.windows.media.ocr import OcrEngine
            from winrt.windows.globalization import Language
            self.engine=OcrEngine.try_create_from_language(Language(language))
            if self.engine is None: self.reason='原生文字辨識語言未安裝'
        except (ImportError,OSError,RuntimeError) as exc:
            self.reason='原生文字辨識不可用：'+str(exc)

    async def recognize(self,image):
        if self.engine is None: return OcrText('',False,self.reason)
        if image is None or not image.size: return OcrText('',False,'辨識區域為空')
        from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode
        from winrt.windows.storage.streams import Buffer
        bitmap=None
        try:
            if image.ndim==2: image=cv2.cvtColor(image,cv2.COLOR_GRAY2BGR)
            bgra=np.ascontiguousarray(cv2.cvtColor(image,cv2.COLOR_BGR2BGRA))
            height,width=bgra.shape[:2]
            buffer=Buffer(bgra.nbytes)
            buffer.length=bgra.nbytes
            memoryview(buffer)[:]=bgra.tobytes()
            bitmap=SoftwareBitmap(BitmapPixelFormat.BGRA8,width,height,BitmapAlphaMode.IGNORE)
            bitmap.copy_from_buffer(buffer)
            result=await self.engine.recognize_async(bitmap)
            return OcrText(result.text,True)
        except (ValueError,OSError,RuntimeError) as exc:
            return OcrText('',False,'原生文字辨識失敗：'+str(exc))
        finally:
            if bitmap is not None: bitmap.close()

    async def read_amount(self,image):
        # 小字先放大；保持原始筆畫，不將字母臆測成數字。
        if image is None or not image.size: return None
        expanded=cv2.resize(image,None,fx=3,fy=3,interpolation=cv2.INTER_CUBIC)
        text=await self.recognize(expanded)
        return parse_amount(text.text) if text.available else None
