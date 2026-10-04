from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextLayout
from ui.fonts import interface_font

def families(text,font):
    layout=QTextLayout(text,font)
    layout.beginLayout()
    layout.createLine()
    layout.endLayout()
    return {run.rawFont().familyName() for run in layout.glyphRuns()}

def test_actual_chinese_and_latin_glyphs_use_requested_fonts(tmp_path):
    from ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.show()
    app.processEvents()
    font=window.analysis.win_label.font()
    assert families('勝率',font)=={'Noto Sans TC'}
    assert families('52.0% ABC',font)=={'Inter'}
    assert families('平手',window.overlay.label.font())=={'Noto Sans TC'}
    assert families('500',window.overlay.label.font())=={'Inter'}
    window.close()
