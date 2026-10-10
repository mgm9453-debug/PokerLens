import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from ui.analysis_panel import AnalysisPanel

def test_waiting_does_not_move_matrix_or_keep_old_probabilities():
    app=QApplication.instance() or QApplication([])
    panel=AnalysisPanel();panel.enable_fixed_layout();panel.resize(700,1100)
    result={'live':True,'hero_cards':['Ah','Ad'],'community_cards':['2c','7s','9d'],
        'call_amount':100,'ev':100,'equity_details':{'win_probability':.7}}
    panel.render(result);panel.show();app.processEvents()
    position=panel.threat_matrix.pos()
    color=panel.threat_matrix.table.item(5,5).background().color().name()
    panel.invalidate('金額正在確認');app.processEvents()
    assert panel.threat_matrix.pos()==position
    assert '更新中' in panel.win_label.text()
    assert not panel.action_label.isHidden()
    assert not panel.sizing_label.isHidden()
    assert panel.summary_scroll.isHidden()
    assert '等待資料確認' in panel.action_label.text()
    assert panel.threat_matrix.caption.text()==''
    assert all(label in panel.threat_matrix.legend.text() for label in ('加注','跟注','過牌','棄牌'))
    assert not panel.threat_matrix.isEnabled()
    assert panel.threat_matrix.table.item(5,5).background().color().name()=='#34373b'
    panel.render(result);app.processEvents()
    assert panel.threat_matrix.pos()==position
    assert panel.threat_matrix.isEnabled()
    assert panel.threat_matrix.table.item(5,5).background().color().name()==color
    assert '70.0%' in panel.win_label.text()
    panel.close()
