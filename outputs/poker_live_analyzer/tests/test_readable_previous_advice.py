import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from ui.analysis_panel import AnalysisPanel

def test_previous_card_uses_distinct_colors_and_fits_its_text():
    app=QApplication.instance() or QApplication([])
    panel=AnalysisPanel();panel.enable_fixed_layout();panel.resize(600,900)
    panel.set_action('依估算建議跟注 1,500','#087d55')
    panel.win_label.setText('勝率 34.4%');panel.tie_label.setText('平手 3.6%')
    panel.sizing_label.setText('需投入 1,500｜當時底池 21%')
    panel.remember_advice();panel.invalidate('缺少必要金額：跟注額')
    panel.show();app.processEvents()
    try:
        text=panel.previous_label.text()
        assert '<br' in text
        assert '#43dfb9' in text and '#c49af5' in text
        assert '非目前結果' in text
        assert panel.previous_label.height()>=panel.previous_label.heightForWidth(panel.previous_label.width())
        assert panel.summary_scroll.isHidden()
        assert '跟注金額' in panel.sizing_label.text()
    finally:panel.close();app.processEvents()

def test_previous_card_preserves_action_color_after_waiting():
    app=QApplication.instance() or QApplication([])
    panel=AnalysisPanel();panel.enable_fixed_layout()
    panel.set_action('棄牌','#c42b36');panel.remember_advice()
    panel.invalidate('沒有可見底牌')
    from ui.action_palette import readable_color
    from control_settings import DEFAULTS
    assert readable_color(DEFAULTS['preflop_fold']) in panel.previous_label.text()
    assert '底牌' in panel.sizing_label.text()
    panel.close()
