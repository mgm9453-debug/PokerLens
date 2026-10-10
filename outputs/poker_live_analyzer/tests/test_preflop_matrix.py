import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from poker.preflop import RangeBook
from ui.threat_matrix import ThreatMatrix


def test_neutral_grid_has_all_centered_white_hands_and_unknown_is_not_fold():
    app = QApplication.instance() or QApplication([])
    matrix = ThreatMatrix()
    matrix.render_preflop({'position': 'UTG', 'hero_cards': ['As','Ks'], 'players': 8})
    assert 'UTG' in matrix.caption.text()
    assert '無對應' in matrix.caption.text()
    for row in range(13):
        for column in range(13):
            item = matrix.table.item(row,column)
            assert item.foreground().color().name() == '#ffffff'
            assert item.background().color().name() == '#34373b'
            assert item.textAlignment() == Qt.AlignCenter
    assert matrix.table.item(0,1).data(Qt.UserRole+2) is True
    matrix.close()


def test_mixed_frequencies_preserved_and_postflop_switches_back():
    app = QApplication.instance() or QApplication([])
    matrix = ThreatMatrix()
    entry = {'format': 'MTT', 'players': 6, 'stack_bb': 40, 'ante_bb': 1,
        'position': 'UTG', 'scenario': 'open', 'open_bb': 2.3,
        'ante_type':'big_blind','payout_model':'chip_ev',
        'opponent_position': None, 'source':'測試', 'license':'測試', 'solver':'測試',
        'hands': {'AA': {'raise':1}, 'AKs': {'raise':.7,'call':.3}, '72o':{'fold':1}}}
    matrix.render_preflop({**entry, 'hero_cards':['As','Ks']}, RangeBook([entry]))
    item = matrix.table.item(0,1)
    assert [fraction for _,fraction in item.data(Qt.UserRole+1)] == [.7,.3]
    assert '加注 70%' in item.toolTip() and '跟注 30%' in item.toolTip()
    assert matrix.table.item(12,7).background().color().name() == '#182333'
    assert matrix.table.item(1,1).background().color().name() == '#34373b'
    matrix.apply_preflop_colors({'preflop_raise':'#701010'})
    assert matrix.table.item(0,0).background().color().name() == '#701010'
    matrix.render(['Ah','Ad'], ['2c','7s','9d'])
    from ui.theme import COLORS
    assert matrix.table.item(5,5).background().color().name() == COLORS['winner'].lower()
    assert not matrix.table.item(0,1).data(Qt.UserRole+2)
    matrix.close()


def test_settings_change_and_invalidation_never_reuse_a_preflop_chart():
    app = QApplication.instance() or QApplication([])
    matrix = ThreatMatrix()
    matrix.render_preflop({'position':'UTG', 'hero_cards':['As','Ks']})
    matrix.apply_colors('#202020', '#881111')
    assert 'UTG' in matrix.caption.text()
    matrix.invalidate()
    assert 'UTG' not in matrix.caption.text()
    assert not matrix.table.item(0,1).data(Qt.UserRole+2)
    assert matrix.table.item(0,1).background().color().name() == '#34373b'
    matrix.apply_preflop_colors({'preflop_background':'#202020'})
    assert not matrix.isEnabled()
    assert matrix.table.item(0,1).background().color().name() == '#202020'
    matrix.close()
