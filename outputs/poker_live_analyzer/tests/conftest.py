import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def pytest_sessionfinish(session, exitstatus):
    """在圖形應用仍存在時清理延後刪除的測試物件，避免原生物件留到直譯器結束。"""
    import gc
    from PySide6.QtCore import QCoreApplication, QEvent
    app=QCoreApplication.instance()
    if app is not None:
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        app.processEvents()
        gc.collect()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
