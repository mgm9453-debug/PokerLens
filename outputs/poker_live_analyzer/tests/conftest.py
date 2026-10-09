import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def pytest_sessionfinish(session, exitstatus):
    """在圖形應用仍存在時清理延後刪除的測試物件，避免原生物件留到直譯器結束。"""
    import gc
    # 純辨識測試未載入圖形介面，不在清理階段額外初始化原生函式庫。
    core=sys.modules.get('PySide6.QtCore')
    if core is None:return
    QCoreApplication,QEvent=core.QCoreApplication,core.QEvent
    app=QCoreApplication.instance()
    if app is not None:
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        app.processEvents()
        gc.collect()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
