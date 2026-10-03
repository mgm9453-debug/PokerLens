import argparse
import ctypes
import os
import sys
from pathlib import Path
from updates.runner import launch, show_error
from updates.security import UpdateError


def activate_existing():
    if os.name != 'nt':
        return False
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
        if isinstance(exc, UpdateError) and str(exc) == '另一個啟動或更新程序正在處理' and activate_existing():
            return 0
        show_error(str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
