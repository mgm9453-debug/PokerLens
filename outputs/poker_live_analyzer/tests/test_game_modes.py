import pytest
from control_settings import validate
from state.models import PokerTableState


def situation():
    return PokerTableState(hero_cards=['As','Ks'],hero_seat=1,pot=100,call_amount=40,
        hero_stack=100,effective_stack=40,players=[
            {'seat':1,'stack':100}, {'seat':2,'stack':0,'current_bet':40,'all_in':True}])


def test_modes_are_saved_and_invalid_modes_rejected():
    for mode in ('cash','tournament','mystery'):
        assert validate({'game_mode':mode})['game_mode']==mode
    with pytest.raises(ValueError): validate({'game_mode':'unknown'})


def test_cash_rake_reduces_call_value():
    from poker.game_modes import assess_mode
    result=assess_mode(situation(),.5,.5,validate({'game_mode':'cash','rake_known':True,'rake_percent':5,'rake_cap':3}))
    assert result['adjusted_call_ev']==pytest.approx(28.5)
    assert result['rake']==3


def test_tournament_does_not_invent_prize_ev():
    from poker.game_modes import assess_mode
    result=assess_mode(situation(),.5,.5,validate({'game_mode':'tournament'}))
    assert result['adjusted_call_ev'] is None
    assert '尚未計入' in result['notice']


def test_bounty_only_counts_confirmed_heads_up_knockout():
    from poker.game_modes import assess_mode
    options=validate({'game_mode':'mystery','bounty_active':True,'bounty_known':True,'bounty_average':20})
    result=assess_mode(situation(),.6,.5,options)
    assert result['bounty_ev']==10
    assert result['adjusted_call_ev'] is None
    assert result['covered_seats']==[2]
    state=situation()
    state.players[1].all_in=False
    assert assess_mode(state,.6,.5,options)['bounty_ev'] is None
    state=situation()
    state.players.append(type(state.players[0])(seat=3,stack=200))
    assert assess_mode(state,.6,.5,options)['bounty_ev'] is None


def test_bounty_inactive_or_unknown_has_no_invented_value():
    from poker.game_modes import assess_mode
    for changes in ({'bounty_active':False},{'bounty_active':True,'bounty_known':False}):
        result=assess_mode(situation(),.6,.5,validate({'game_mode':'mystery',**changes}))
        assert result['bounty_ev'] is None


def test_single_mode_ignores_old_mode_settings(tmp_path):
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow
    from control_settings import write
    app=QApplication.instance() or QApplication([])
    write(validate({'game_mode':'mystery','bounty_active':True,'bounty_known':True}),tmp_path/'control_settings.json')
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    try:
        assert not hasattr(window,'game_mode')
        window.overlay.render({'mode_analysis':{'label':'神秘寶箱','notice':'賞金尚未啟動'}},situation().to_dict())
        assert '神秘寶箱' not in window.overlay.details.text()
        from ui.control_dialog import ControlDialog
        dialog=ControlDialog(window.control_options,lambda _:None,lambda:'',window)
        assert 'game_mode' not in dialog.fields
        assert 'bounty_known' not in dialog.fields
        dialog.close()
    finally:
        window.close()


def test_old_mode_result_does_not_override_single_analysis():
    from PySide6.QtWidgets import QApplication
    from ui.analysis_panel import AnalysisPanel
    app=QApplication.instance() or QApplication([])
    panel=AnalysisPanel()
    try:
        panel.render({'live':True,'call_amount':40,'equity':.6,'ev':44,
            'mode_analysis':{'mode':'tournament','label':'一般錦標賽','notice':'舊結果'},
            'spr':1,'tie_probability':0,'equity_details':{'win_probability':.5},
            'hero_cards':['As','Ks'],'community_cards':['Ah','8s','3s']})
        assert '跟注 40' in panel.action_label.text()
        assert not panel.mode_notice.text()
        assert '底牌已確認' in panel.card_text.text()
        assert panel.threat_matrix.table.rowCount()==13
        assert panel.hero_picture.pixmap().isNull()
    finally:
        panel.close()
