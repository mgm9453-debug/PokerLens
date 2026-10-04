from ui.window_placement import free_regions,choose_region

def test_right_sidebar_stays_outside_table_and_taskbar():
    areas=free_regions((0,0,1920,1040),(0,0,1128,799))
    rect=choose_region(areas,600,500)
    assert rect[0]>=1138
    assert rect[0]+rect[2]<=1920
    assert rect[1]+rect[3]<=1040

def test_left_sidebar_and_negative_monitor_origin():
    rect=choose_region(free_regions((-1920,0,1920,1040),(-1100,0,-100,799)),600,500)
    assert rect[0]>=-1920
    assert rect[0]+rect[2]<=-1110

def test_fullscreen_table_has_no_nonoverlapping_region():
    assert choose_region(free_regions((0,0,1920,1040),(0,0,1920,1040)),380,260) is None


def test_main_window_docks_without_covering_table_and_can_disable(tmp_path,monkeypatch):
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow
    from capture.window_capture import TableWindow
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.set_live_layout()
    window.auto_active=True
    table=TableWindow(99,'盲注 50/100',(0,0,1128,799))
    class Screen:
        def availableGeometry(self):return QRect(0,0,1920,1040)
    monkeypatch.setattr('ui.window_placement.table_screen',lambda *_:(Screen(),table.rect))
    try:
        window.dock_beside_table(table)
        app.processEvents()
        frame=window.frameGeometry()
        assert frame.left()>1128
        assert frame.right()<1920
        assert frame.bottom()<1040
        position=window.pos()
        window.control_options['auto_dock']=False
        window.dock_key=None
        window.dock_beside_table(table)
        assert window.pos()==position
    finally:
        window.close()
