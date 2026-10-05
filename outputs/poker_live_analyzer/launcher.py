import argparse
import ctypes
import hashlib
import logging
import os
import sys
import time
from pathlib import Path
from updates.runner import launch, show_error
from updates.security import UpdateError


def request_activation(directory):
    """透過同一份資料的視窗連線喚回，不依賴隱藏視窗的標題。"""
    if os.name != 'nt':return False
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel.CreateFileW.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.PeekNamedPipe.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p,ctypes.POINTER(wintypes.DWORD),ctypes.c_void_p]
    kernel.ReadFile.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),ctypes.c_void_p]
    name='PokerLens-'+hashlib.sha256(str(directory).encode()).hexdigest()[:20]
    handle=kernel.CreateFileW('\\\\.\\pipe\\'+name,0xc0000000,0,None,3,0,None)
    if handle==ctypes.c_void_p(-1).value:return False
    try:
        deadline=time.monotonic()+1
        while time.monotonic()<deadline:
            available=wintypes.DWORD()
            if not kernel.PeekNamedPipe(handle,None,0,None,ctypes.byref(available),None):return False
            if available.value:
                buffer=ctypes.create_string_buffer(32);count=wintypes.DWORD()
                return bool(kernel.ReadFile(handle,buffer,32,ctypes.byref(count),None)) and buffer.raw[:count.value]==b'shown'
            time.sleep(.02)
        return False
    finally:kernel.CloseHandle(handle)


def activate_existing(directory):
    if os.name != 'nt':
        return False
    if request_activation(directory):
        logging.info('已透過程式連線喚回主視窗')
        return True
    user = ctypes.windll.user32
    user.FindWindowW.restype = ctypes.c_void_p
    window = user.FindWindowW(None, 'PokerLens')
    if not window:
        return False
    user.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user.ShowWindow(window, 9)
    user.SetForegroundWindow(window)
    return True


def main():
    parser = argparse.ArgumentParser(description='PokerLens 固定啟動入口')
    parser.add_argument('--root', type=Path)
    parser.add_argument('--data', type=Path)
    args = parser.parse_args()
    root = args.root or Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
    data = args.data or Path(os.environ.get('LOCALAPPDATA', str(Path.home())))/'PokerLens'
    try:
        return launch(root, data)
    except (UpdateError, OSError) as exc:
        if isinstance(exc, UpdateError) and str(exc) == '另一個啟動或更新程序正在處理' and activate_existing(data):
            return 0
        show_error(str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
