import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint,Qt
from ui.main_window import MainWindow


def test_matrix_remains_fully_visible_at_allowed_sizes(tmp_path):
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.set_live_layout()
    window.analysis.set_action('依估算建議跟注 1,500','#087d55')
    window.analysis.win_label.setText('勝率 34.4%')
    window.analysis.tie_label.setText('平手 3.6%')
    window.analysis.sizing_label.setText('目前下注：跟注 1,500｜目前底池 21%｜依設定的對手範圍估算')
    window.analysis.remember_advice()
    window.analysis.invalidate('等待牌桌；開啟牌局後會自動追蹤。')
    window.show()
    try:
        for width,height in ((640,900),(780,960),(1000,900),(1000,1000)):
            window.resize(width,height)
            for _ in range(8):app.processEvents()
            table=window.analysis.threat_matrix.table
            bottom=table.mapTo(window.main_scroll.viewport(),QPoint(0,table.height()))
            assert table.horizontalScrollBar().maximum()==0
            assert table.verticalScrollBar().maximum()==0
            assert bottom.y()<=window.main_scroll.viewport().height()
            previous=window.analysis.previous_label
            assert previous.height()>=previous.heightForWidth(previous.width())
            assert table.rowCount()==table.columnCount()==13
            assert all(table.item(row,column) is not None for row in range(13) for column in range(13))
        window.resize(300,300)
        app.processEvents()
        assert window.width()>=640 and window.height()>=900
        assert not window.windowFlags() & Qt.WindowMinimizeButtonHint
    finally:
        window.close()
        app.processEvents()
