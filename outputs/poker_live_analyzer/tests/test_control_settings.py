import pytest
from control_settings import read,write,validate

def test_save_and_reopen_exact_settings(tmp_path):
    path=tmp_path/'設定.json'
    options=validate({'action_font':36,'opponent_range':'loose','iterations':100000,'bet_percentages':[33,75,150]})
    write(options,path)
    assert read(path)==options
    assert not path.with_suffix('.tmp').exists()

@pytest.mark.parametrize('bad',[[],{'action_font':999},{'show_chips':1},{'win_color':'red'},
    {'bet_percentages':[]},{'bet_percentages':[33,33]},{'bet_percentages':[{}]}, {'iterations':12345}])
def test_invalid_settings_do_not_replace_valid_file(tmp_path,bad):
    path=tmp_path/'設定.json'
    write({},path)
    previous=read(path)
    with pytest.raises(ValueError): write(bad,path)
    assert read(path)==previous

def test_custom_bet_proportions_reach_calculation():
    from poker.bet_simulator import simulate_bets
    rows=simulate_bets(1000,3000,.6,percentages=[33,75,150])
    assert [row.percentage for row in rows]==[33,75,150]
    assert [row.bet for row in rows]==[330,750,1500]

def test_dialog_cancel_restore_apply_and_runtime_effects(tmp_path):
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow
    from ui.control_dialog import ControlDialog
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    initial=dict(window.control_options)
    dialog=ControlDialog(initial,window.save_control_settings,window.capture_status,window)
    dialog.fields['action_font'].setValue(36)
    dialog.reject()
    assert window.control_options==initial
    dialog.apply()
    assert window.control_options['action_font']==36
    assert '36px' in window.analysis.action_label.styleSheet()
    assert read(window.control_path)['action_font']==36
    dialog.load(validate({}))
    assert window.control_options['action_font']==36
    dialog.apply()
    assert window.control_options==validate({})
    write(validate({'probability_font':40,'show_chips':False}),window.control_path)
    window.poll_control_settings()
    assert '40px' in window.analysis.win_label.styleSheet()
    assert window.live_numbers.isHidden()
    assert '視窗內容擷取' in window.capture_status()
    window.close()

@pytest.mark.parametrize('change',[{'iterations':10000},{'bet_percentages':[33,75]}])
def test_analysis_parameter_changes_restart_when_table_is_unchanged(tmp_path,change):
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow
    from tests.test_live_state import inputs
    from vision.live_state import LiveStateAssembler
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.auto_active=True
    calls=[]
    window.start_analysis=lambda:calls.append(True)
    window.accept_auto_table(window.auto_generation,LiveStateAssembler().build(*inputs()))
    window.result=object()
    calls.clear()
    window.apply_control_options(validate(change))
    assert calls==[True]
    window.close()

def test_live_range_setting_reaches_state_and_refresh_reaches_worker(tmp_path):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow
    from tests.test_live_state import inputs
    from vision.live_state import LiveStateAssembler
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.auto_active=True
    calls=[]
    window.start_analysis=lambda:calls.append(window.detector.version)
    window.accept_auto_table(window.auto_generation,LiveStateAssembler().build(*inputs()))
    window.vision_worker=SimpleNamespace(refresh_ms=100)
    window.apply_control_options(validate({'opponent_range':'loose','refresh_ms':500,'iterations':10000}))
    assert set(window.detector.state.ranges.values())=={'loose'}
    assert window.vision_worker.refresh_ms==500
    assert window.settings.iterations.currentData()==10000
    assert len(calls)>=2
    window.vision_worker=None
    window.close()
