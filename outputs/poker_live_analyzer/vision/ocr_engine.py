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

def blinds_from_title(text):
    match=re.search(r'(?:盲注|blinds?)\s*([\d,]+)\s*/\s*([\d,]+)',text,re.I)
    if not match: return None
    small,big=(float(v.replace(',','')) for v in match.groups())
    return (small,big) if 0<small<=big else None


def parse_amount(text,big_blind=None):
    text=unicodedata.normalize('NFKC',text).strip()
    if re.search(r'BB\b',text,re.I):
        match=re.fullmatch(r'(?:底\s*池\s*[:：]?\s*|pot\s*[:：]?\s*)?(\d+(?:\.\d+)?)\s*BB',text,re.I)
        if not match or big_blind is None or not np.isfinite(big_blind) or big_blind<=0: return None
        value=float(match[1])*big_blind
        return value if np.isfinite(value) and value<=1e12 else None
    if '-' in text or re.search(r'\d[A-Za-z]\d',text): return None
    numbers=re.findall(r'(?<![\w.])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w.,])',text)
    if len(numbers)!=1: return None
    value=float(numbers[0].replace(',',''))
    return value if np.isfinite(value) and 0<=value<=1e12 else None


def unique_amount(texts,big_blind=None):
    values={value for text in texts if (value:=parse_amount(text,big_blind)) is not None}
    return values.pop() if len(values)==1 else None

class NativeOcrEngine:
    def __init__(self,language='en-US',big_blind=None):
        self.big_blind=big_blind
        self.bb_display=False
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
        self.bb_display=self.bb_display or bool(re.search(r'BB\b',text.text,re.I))
        value=parse_amount(text.text,self.big_blind) if text.available else None
        if value is None and text.available and text.text:
            # 不把錯讀的字母改成數字，改以另一種縮放重新讀原始筆畫。
            alternate=await self.recognize(cv2.resize(image,None,fx=3,fy=3,interpolation=cv2.INTER_LINEAR))
            self.bb_display=self.bb_display or bool(re.search(r'BB\b',alternate.text,re.I))
            value=parse_amount(alternate.text,self.big_blind) if alternate.available else None
        if value is None:
            # 用亮度對比處理文字，不依賴桌布的藍、綠、紫或木紋色相。
            gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY) if image.ndim==3 else image
            if float(gray.std())<2: return None
            binary=cv2.threshold(gray,0,255,cv2.THRESH_BINARY|cv2.THRESH_OTSU)[1]
            texts=[]
            for prepared in (gray,binary,255-binary):
                prepared=cv2.copyMakeBorder(prepared,10,10,10,10,cv2.BORDER_CONSTANT,value=int(prepared[0,0]))
                result=await self.recognize(cv2.resize(prepared,None,fx=3,fy=3,interpolation=cv2.INTER_LINEAR))
                self.bb_display=self.bb_display or bool(re.search(r'BB\b',result.text,re.I))
                if result.available: texts.append(result.text)
            value=unique_amount(texts,self.big_blind)
        return value

    async def read_pot_amount(self,image):
        """先讀原圖，再隔離常見底池文字筆畫；不把桌布色當成底池。"""
        value=await self.read_amount(image)
        if image is None or not image.size: return None
        hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
        texts=[]
        for threshold in (160,180):
            mask=np.uint8((hsv[:,:,0]>15)&(hsv[:,:,0]<40)&(hsv[:,:,1]>90)&(hsv[:,:,2]>threshold))*255
            if np.count_nonzero(mask)<10: continue
            prepared=cv2.copyMakeBorder(255-mask,10,10,10,10,cv2.BORDER_CONSTANT,value=255)
            text=await self.recognize(cv2.resize(prepared,None,fx=3,fy=3,interpolation=cv2.INTER_CUBIC))
            texts.append(text.text.strip(' :：'))
            self.bb_display=self.bb_display or bool(re.search(r'BB\b',text.text,re.I))
        # 有效候選必須一致；不同處理得到不同金額時不採用。
        isolated=unique_amount(texts,self.big_blind)
        return isolated if isolated is not None else value

    async def read_amount_matching(self,image,expected):
        """須由至少兩種文字處理確認差額，不把猜測的金額塞回辨識結果。"""
        if image is None or not image.size:return None
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY) if image.ndim==3 else image
        binary=cv2.threshold(gray,0,255,cv2.THRESH_BINARY|cv2.THRESH_OTSU)[1]
        matches=0
        for prepared in (gray,binary,255-binary):
            prepared=cv2.copyMakeBorder(prepared,10,10,10,10,cv2.BORDER_CONSTANT,value=int(prepared[0,0]))
            result=await self.recognize(cv2.resize(prepared,None,fx=3,fy=3,interpolation=cv2.INTER_LINEAR))
            self.bb_display=self.bb_display or bool(re.search(r'BB\b',result.text,re.I))
            value=parse_amount(result.text,self.big_blind) if result.available else None
            if value is not None and abs(value-expected)<=.01:matches+=1
        return expected if matches>=2 else None

    async def locate_pot(self,image):
        """移位底池只採用帶有底池標籤的文字區，避免抓到下注與籌碼。"""
        hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
        yellow=np.uint8((hsv[:,:,0]>15)&(hsv[:,:,0]<40)&(hsv[:,:,1]>90)&(hsv[:,:,2]>160))*255
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        # 明暗筆畫來源不限定金色文字；背景紋理也可能入選，但必須通過標籤檢查。
        strokes=cv2.max(cv2.morphologyEx(gray,cv2.MORPH_TOPHAT,np.ones((9,9),np.uint8)),
            cv2.morphologyEx(gray,cv2.MORPH_BLACKHAT,np.ones((9,9),np.uint8)))
        generic=cv2.threshold(strokes,0,255,cv2.THRESH_BINARY|cv2.THRESH_OTSU)[1]
        candidates=[]
        language=NativeOcrEngine('zh-TW',big_blind=self.big_blind)
        for mask in (yellow,generic):
            joined=cv2.dilate(mask,np.ones((3,15),np.uint8))
            contours,_=cv2.findContours(joined,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            for contour in sorted(contours,key=cv2.contourArea,reverse=True)[:8]:
                x,y,w,h=cv2.boundingRect(contour)
                if not (40<=w<=image.shape[1]*.8 and 8<=h<=image.shape[0]*.2): continue
                region=image[max(0,y-8):y+h+8,max(0,x-8):x+w+8]
                text_mask=mask[max(0,y-8):y+h+8,max(0,x-8):x+w+8]
                prepared=cv2.copyMakeBorder(255-text_mask,10,10,10,10,cv2.BORDER_CONSTANT,value=255)
                resized=cv2.resize(prepared,None,fx=3,fy=3)
                label=await language.recognize(resized)
                if '底池' not in re.sub(r'\s','',label.text):
                    english=await self.recognize(resized)
                    if not re.search(r'\bpot\b',english.text,re.I): continue
                value=await self.read_pot_amount(region)
                if value is not None: candidates.append(value)
        return candidates[0] if candidates and len(set(candidates))==1 else None
