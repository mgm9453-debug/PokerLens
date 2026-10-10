import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from ui.analysis_panel import AnalysisPanel

def panel():
    app=QApplication.instance() or QApplication([])
    p=AnalysisPanel();p.enable_fixed_layout()
    return app,p

def test_previous_result_survives_invalidation_as_explicit_history():
    app,p=panel()
    p.set_action('跟注 500','#087d55')
    p.win_label.setText('勝率 60.0%');p.tie_label.setText('平手 2.0%')
    p.sizing_label.setText('需補 500｜底池 25%')
    p.remember_advice()
    p.invalidate('牌桌資料已逾期')
    assert '上一次' in p.previous_label.text()
    assert '跟注 500' in p.previous_label.text()
    assert '60.0%' in p.previous_label.text()
    assert '跟注 500' not in p.action_label.text()
    p.close()

def test_same_context_refresh_keeps_visible_result():
    app,p=panel()
    p.set_action('跟注 500','#087d55');p.win_label.setText('勝率 60.0%')
    p.begin_refresh(True)
    assert p.action_label.text()=='跟注 500'
    assert p.win_label.text()=='勝率 60.0%'
    p.close()

def test_highlight_only_action_or_size_changes():
    app,p=panel()
    p.set_action('跟注 500','#087d55');p.sizing_label.setText('需補 500')
    p.remember_advice()
    assert p.reminder_timer.isActive()
    p.reminder_timer.stop()
    p.win_label.setText('勝率 60.1%');p.remember_advice()
    assert not p.reminder_timer.isActive()
    p.close()
