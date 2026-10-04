"""只調整分析器視窗，避開牌桌及工作列。"""

def free_regions(available,table,gap=10):
    x,y,w,h=available
    right,bottom=x+w,y+h
    left,top,tr,tb=table
    return [(max(x,tr+gap),y,max(0,right-max(x,tr+gap)),h),
        (x,y,max(0,min(right,left-gap)-x),h),
        (x,max(y,tb+gap),w,max(0,bottom-max(y,tb+gap))),
        (x,y,w,max(0,min(bottom,top-gap)-y))]

def choose_region(regions,width,height):
    return next((rect for rect in regions if rect[2]>=width and rect[3]>=height),None)

def table_screen(table,screens):
    # 擷取座標為實體像素；依所在螢幕原點與縮放換成介面座標。
    import sys
    if sys.platform=='win32':
        import ctypes
        from ctypes import wintypes
        class MonitorInfo(ctypes.Structure):
            _fields_=[('size',wintypes.DWORD),('monitor',wintypes.RECT),
                ('work',wintypes.RECT),('flags',wintypes.DWORD),('device',wintypes.WCHAR*32)]
        user=ctypes.WinDLL('user32',use_last_error=True)
        user.MonitorFromWindow.argtypes=[wintypes.HWND,wintypes.DWORD]
        user.MonitorFromWindow.restype=wintypes.HANDLE
        user.GetMonitorInfoW.argtypes=[wintypes.HANDLE,ctypes.POINTER(MonitorInfo)]
        info=MonitorInfo();info.size=ctypes.sizeof(info)
        monitor=user.MonitorFromWindow(table.handle,2)
        if user.GetMonitorInfoW(monitor,ctypes.byref(info)):
            screen=next((screen for screen in screens if screen.name()==info.device),None)
            if screen is not None:
                geometry=screen.geometry();ratio=screen.devicePixelRatio()
                left,top,right,bottom=table.rect
                return screen,(round(geometry.x()+(left-info.monitor.left)/ratio),
                    round(geometry.y()+(top-info.monitor.top)/ratio),
                    round(geometry.x()+(right-info.monitor.left)/ratio),
                    round(geometry.y()+(bottom-info.monitor.top)/ratio))
    screen=screens[0]
    return screen,table.rect
