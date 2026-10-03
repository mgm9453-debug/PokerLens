"""只讀牌桌視窗追蹤與畫面擷取；不移動視窗或輸入任何操作。"""
from contextlib import contextmanager
from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import math
import ntpath
import os
import sys

import mss
import numpy as np


DEFAULT_REGIONS = ((.40, .68, .22, .20), (.27, .35, .46, .24))


@dataclass(frozen=True)
class TableWindow:
    handle: int
    title: str
    rect: tuple[int, int, int, int]


def region_rect(rect, region):
    left, top, right, bottom = rect
    x, y, width, height = region
    if right <= left or bottom <= top:
        raise ValueError('視窗尺寸無效')
    if not all(math.isfinite(v) for v in region) or min(region) < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
        raise ValueError('保護區域必須位於畫面內')
    return (left + round(x * (right-left)), top + round(y * (bottom-top)),
            left + round((x+width) * (right-left)), top + round((y+height) * (bottom-top)))


def regions_occluded(rect, regions, obstacles):
    for region in regions:
        a = region_rect(rect, region)
        for b in obstacles:
            if min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1]):
                return True
    return False


def _apis():
    if sys.platform != 'win32':
        raise RuntimeError('牌桌視窗擷取只支援 Windows')
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetWindow.restype = wintypes.HWND
    user.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    for name in ('IsWindow', 'IsWindowVisible', 'IsIconic'):
        getattr(user, name).argtypes = [wintypes.HWND]
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    return user, kernel


@contextmanager
def _physical_coordinates():
    user, _ = _apis()
    previous = user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    if not previous:
        raise RuntimeError('無法取得實體像素座標')
    try:
        yield user
    finally:
        user.SetThreadDpiAwarenessContext(previous)


def _rect(user, handle):
    rect = wintypes.RECT()
    if not user.GetWindowRect(handle, ctypes.byref(rect)):
        raise RuntimeError('無法讀取牌桌視窗位置')
    return rect.left, rect.top, rect.right, rect.bottom


def _is_target(user, kernel, handle):
    pid = wintypes.DWORD()
    user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
    process = kernel.OpenProcess(0x1000, False, pid.value)
    if not process:
        return False
    try:
        name = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(name))
        return bool(kernel.QueryFullProcessImageNameW(process, 0, name, ctypes.byref(size))) and ntpath.basename(name.value).casefold() == 'wpt global.exe'
    finally:
        kernel.CloseHandle(process)


def list_tables():
    result = []
    with _physical_coordinates() as user:
        _, kernel = _apis()
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(handle, parameter):
            if user.IsWindowVisible(handle) and _is_target(user, kernel, handle):
                title = ctypes.create_unicode_buffer(user.GetWindowTextLengthW(handle) + 1)
                user.GetWindowTextW(handle, title, len(title))
                if title.value.strip():
                    rect = _rect(user, handle)
                    if rect[2] > rect[0] and rect[3] > rect[1]:
                        result.append(TableWindow(int(handle), title.value, rect))
            return True
        user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        if not user.EnumWindows(callback_type(visit), 0):
            raise RuntimeError('無法列舉牌桌視窗')
    def priority(table):
        hint = any(text in table.title.casefold() for text in ('盲注', '底池', 'blind', 'pot', '$'))
        area = (table.rect[2]-table.rect[0]) * (table.rect[3]-table.rect[1])
        return hint, area
    return sorted(result, key=priority, reverse=True)


def _validated_rect(handle, regions):
    with _physical_coordinates() as user:
        _, kernel = _apis()
        if not user.IsWindow(handle) or not user.IsWindowVisible(handle) or not _is_target(user, kernel, handle):
            raise RuntimeError('找不到所選牌桌，請重新選擇')
        if user.IsIconic(handle):
            raise RuntimeError('牌桌已最小化，請還原視窗')
        rect = _rect(user, handle)
        if not regions:
            return rect
        obstacles = []
        above = user.GetWindow(handle, 3)
        while above:
            if user.IsWindowVisible(above) and not user.IsIconic(above):
                other = _rect(user, above)
                name = ctypes.create_unicode_buffer(256)
                user.GetClassNameW(above, name, len(name))
                style = user.GetWindowLongW(above, -20)
                tooltip = name.value == 'tooltips_class32' and (other[2]-other[0])*(other[3]-other[1]) < 20000
                pid = wintypes.DWORD()
                user.GetWindowThreadProcessId(above, ctypes.byref(pid))
                transparent_overlay = pid.value == os.getpid() and bool(style & 0x20 and style & 0x80000)
                if not tooltip and not transparent_overlay:
                    obstacles.append(other)
            above = user.GetWindow(above, 3)
        if regions_occluded(rect, regions, obstacles):
            raise RuntimeError('底牌或公共牌被其他視窗遮住，請移開遮擋視窗')
        return rect


class WindowCapture:
    def __init__(self, handle, protected_regions=DEFAULT_REGIONS):
        self.handle = int(handle)
        self.protected_regions = tuple(tuple(region) for region in protected_regions)
        for region in self.protected_regions:
            region_rect((0, 0, 1000, 1000), region)
        self._source = None

    def open(self):
        self.close()
        _validated_rect(self.handle, self.protected_regions)
        try:
            with _physical_coordinates():
                self._source = mss.MSS()
        except Exception as error:
            raise RuntimeError('無法開啟牌桌畫面擷取') from error

    def read(self):
        if self._source is None:
            raise RuntimeError('牌桌擷取尚未開啟')
        rect = _validated_rect(self.handle, self.protected_regions)
        left, top, right, bottom = rect
        if right <= left or bottom <= top:
            raise RuntimeError('牌桌視窗尺寸無效')
        try:
            frame = np.asarray(self._source.grab({'left': left, 'top': top, 'width': right-left, 'height': bottom-top}))[:, :, :3].copy()
        except Exception as error:
            raise RuntimeError('無法讀取牌桌畫面') from error
        if _validated_rect(self.handle, self.protected_regions) != rect:
            raise RuntimeError('牌桌位置正在變動，請等待下一幀')
        return frame

    def close(self):
        if self._source is not None:
            self._source.close()
            self._source = None
