"""產品資訊唯一來源，執行時與打包工具共用。"""
import json
import sys
from pathlib import Path

PRODUCT_PATH = ((Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False)
                 else Path(__file__).resolve().parent) / 'release' / 'product.json')
if not PRODUCT_PATH.is_file():
    PRODUCT_PATH = Path(__file__).resolve().parent / 'release' / 'product.json'
PRODUCT = json.loads(PRODUCT_PATH.read_text(encoding='utf-8'))
CURRENT_VERSION = PRODUCT['version']
APP_NAME = PRODUCT['name']
PUBLISHER = PRODUCT['publisher']
APP_ID = PRODUCT['app_id']
