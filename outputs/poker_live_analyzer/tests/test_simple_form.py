import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_form_builds_valid_state_without_codes(app):
    from ui.simple_form import SimpleHandForm
    from state.table_state import PokerTableState
    form = SimpleHandForm()
    form.hero[0].set_card('As')
    form.hero[1].set_card('Ks')
    for button, card in zip(form.board, ['Ah','8s','3s']):
        button.set_card(card)
    form.pot.setValue(2000)
    form.call.setValue(800)
    form.stack.setValue(8000)
    state = PokerTableState.from_dict(form.to_data())
    assert state.hero_cards == ['As','Ks']
    assert state.community_cards == ['Ah','8s','3s']
    assert state.call_amount == 800
    assert state.players[1].current_bet == 800


def test_form_rejects_incomplete_board_and_missing_hero(app):
    from ui.simple_form import SimpleHandForm
    form = SimpleHandForm()
    with pytest.raises(ValueError, match='底牌'):
        form.to_data()
    form.hero[0].set_card('As')
    form.hero[1].set_card('Ks')
    form.board[0].set_card('Ah')
    with pytest.raises(ValueError, match='公共牌'):
        form.to_data()


def test_form_can_clear_and_load_demo(app):
    from ui.simple_form import SimpleHandForm
    from ui.main_window import demo_data
    form = SimpleHandForm()
    form.load_data(demo_data())
    assert form.hero[0].text() == 'A♠'
    assert form.pot.value() == 20
    form.clear()
    assert all(button.card is None for button in form.hero + form.board)
    assert form.pot.value() == 0


def test_card_picker_excludes_used_cards(app):
    from ui.simple_form import CardPicker
    picker = CardPicker('選擇底牌', {'As','Ks'})
    assert not picker.buttons['As'].isEnabled()
    assert picker.buttons['Ah'].isEnabled()


def test_default_window_hides_advanced_controls(app, tmp_path):
    from ui.main_window import MainWindow
    window = MainWindow(data_dir=tmp_path, auto_demo=False)
    window.show()
    app.processEvents()
    assert window.simple_form.isVisible()
    assert not window.advanced.isVisible()
    assert not window.editor.isVisible()
    window.advanced_toggle.setChecked(True)
    assert window.advanced.isVisible()
    window.close()


def test_simple_analysis_preserves_advanced_player_details(app):
    from ui.simple_form import SimpleHandForm
    from ui.main_window import demo_data
    data = demo_data()
    data['players'][1]['name'] = '對手甲'
    form = SimpleHandForm()
    form.load_data(data)
    result = form.to_data()
    assert result['small_blind'] == .5
    assert result['dealer_position'] == 2
    assert result['players'][1]['name'] == '對手甲'
    assert result['players'][1]['total_invested'] == 9


def test_user_can_select_card_from_dialog(app):
    from ui.simple_form import SimpleHandForm
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtTest import QTest
    form = SimpleHandForm()
    form.show()
    QTimer.singleShot(0, lambda: app.activeModalWidget().buttons['As'].click())
    QTest.mouseClick(form.hero[0], Qt.MouseButton.LeftButton)
    assert form.hero[0].card == 'As'
    form.close()


def test_simple_button_analyzes_and_clear_removes_results(app, tmp_path):
    from ui.main_window import MainWindow
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    window = MainWindow(data_dir=tmp_path, auto_demo=False)
    window.show()
    window.settings.iterations.setCurrentIndex(0)
    window.clear_simple()
    window.simple_form.hero[0].set_card('As')
    window.simple_form.hero[1].set_card('Ks')
    window.simple_form.pot.setValue(300)
    window.simple_form.call.setValue(100)
    window.simple_form.stack.setValue(1000)
    QTest.mouseClick(window.analyze_button, Qt.MouseButton.LeftButton)
    for _ in range(300):
        QTest.qWait(20)
        if window.result:
            break
    assert window.result is not None, window.statusBar().currentMessage()
    assert window.detector.state.call_amount == 100
    window.clear_simple()
    window.return_live()
    assert window.result is None
    assert all(button.card is None for button in window.simple_form.hero)
    assert '分析' in window.analysis.summary.text()
    window.close()


def test_history_replay_matches_visible_cards(app, tmp_path):
    from ui.main_window import MainWindow, demo_data
    from state.table_state import PokerTableState
    window = MainWindow(data_dir=tmp_path, auto_demo=False)
    data = demo_data()
    event = window.detector.update(PokerTableState.from_dict(data))
    window.repository.save_event(event)
    data['hero_cards'] = ['Qs','Qd']
    event = window.detector.update(PokerTableState.from_dict(data))
    window.repository.save_event(event)
    window.sync_form(window.detector.state.to_dict())
    window.refresh_history()
    window.replay(window.history.item(0))
    assert window.simple_form.hero[0].card == 'As'
    window.return_live()
    assert window.simple_form.hero[0].card == 'Qs'
    window.close()
