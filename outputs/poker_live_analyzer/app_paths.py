"""唯讀程式資源與可寫使用者資料分開存放。"""
import os
import sys
from pathlib import Path

def resource_path(relative):
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent / relative
    return Path(__file__).resolve().parent / relative

def user_data_dir():
    # 覆寫只供隔離驗證，不影響正式預設路徑。
    override = os.environ.get('POKERLENS_DATA_DIR')
    if override:
        return Path(override).resolve()
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'PokerLens'

def install_root():
    if getattr(sys, 'frozen', False):
        executable = Path(sys.executable).resolve()
        if executable.parent.parent.name == 'versions':
            return executable.parent.parent.parent
    return None

def prepare_data_dir():
    root = user_data_dir()
    for name in ('profiles', 'ranges', 'logs', 'cache', 'backups'):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root
