from ui.threat_matrix import winning_cells, hand_key

def test_matrix_uses_suits_and_pairs():
    assert hand_key(('As','Ks'))=='AKs'
    assert hand_key(('Kh','As'))=='AKo'
    assert hand_key(('8h','8c'))=='88'

def test_no_current_threat_before_flop():
    assert winning_cells(('As','Ks'),())=={}

def test_royal_flush_cannot_be_beaten():
    assert winning_cells(('As','Ks'),('Qs','Js','Ts'))=={}

def test_pair_matrix_marks_winners_and_excludes_blocked_cards():
    cells=winning_cells(('Ah','Ad'),('2c','7s','9d'))
    assert '99' in cells and '77' in cells
    assert 'KK' not in cells
    assert all(not set(hand)&{'Ah','Ad','2c','7s','9d'} for hands in cells.values() for hand in hands)


def test_colors_persist_and_update_without_changing_cards(tmp_path):
    from control_settings import write,read
    from PySide6.QtWidgets import QApplication
    from ui.threat_matrix import ThreatMatrix
    app=QApplication.instance() or QApplication([])
    path=tmp_path/'settings.json'
    write({'matrix_background':'#121212','matrix_winner':'#33cc99'},path)
    options=read(path)
    matrix=ThreatMatrix()
    matrix.render(['Ah','Ad'],['2c','7s','9d'])
    matrix.apply_colors(options['matrix_background'],options['matrix_winner'])
    assert matrix.table.item(1,1).background().color().name()=='#121212'
    assert matrix.table.item(1,1).foreground().color().name()=='#ffffff'
    assert matrix.table.item(5,5).background().color().name()=='#33cc99'
    assert matrix.table.item(5,5).foreground().color().name()=='#000000'
    matrix.close()
