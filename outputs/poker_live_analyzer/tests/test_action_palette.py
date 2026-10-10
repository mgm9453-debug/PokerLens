"""驗證使用者改色後，行動、圖例、矩陣與浮窗保持一致。"""
from PySide6.QtWidgets import QApplication
from control_settings import validate
from ui.analysis_panel import AnalysisPanel
from ui.table_overlay import TableOverlay
from ui.action_palette import readable_color

def test_custom_colors_reach_all_action_surfaces():
    app=QApplication.instance() or QApplication([])
    panel=AnalysisPanel();panel.dark_theme=True;panel.enable_fixed_layout()
    overlay=TableOverlay()
    options=validate({'preflop_raise':'#e96779','preflop_call':'#4edab3','preflop_check':'#efcf77','preflop_fold':'#182333'})
    panel.apply_display_options(options);overlay.apply_display_options(options)
    for word,role,legacy,key in [('加注','raise_color','#df5969','preflop_raise'),('跟注','call_color','#087d55','preflop_call'),('過牌','check_color','#1765aa','preflop_check'),('棄牌','fold_color','#c42b36','preflop_fold')]:
        panel.set_action(word,legacy)
        assert panel.action_label.property('role_color')==role
        color=readable_color(options[key])
        assert color in panel.action_label.styleSheet()
        assert color in panel.threat_matrix.legend.text()
        assert panel.threat_matrix.preflop_colors[key]==options[key]
        overlay.render({'action_text':word,'action_role':role},{'call_amount':0,'pot':1})
        assert color in overlay.label.styleSheet()
    changed=validate({**options,'preflop_call':'#f2ad66'})
    panel.set_action('跟注','#087d55');overlay.render({'action_text':'跟注','action_role':'call_color'},{})
    panel.apply_display_options(changed);overlay.apply_display_options(changed)
    assert '#f2ad66' in panel.action_label.styleSheet()
    assert '#f2ad66' in overlay.label.styleSheet()
    assert '#f2ad66' in panel.threat_matrix.legend.text()
    panel.close();overlay.close()

def test_legacy_colors_are_imported_without_overriding_chart_colors():
    assert validate({'call_color':'#aabbcc'})['preflop_call']=='#aabbcc'
    options=validate({'call_color':'#aabbcc','preflop_call':'#112233'})
    assert options['preflop_call']==options['call_color']=='#112233'


def test_explicit_custom_color_is_not_replaced_by_old_default():
    assert validate({'preflop_check':'#655124'})['preflop_check']=='#655124'
