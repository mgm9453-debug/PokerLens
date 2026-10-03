from itertools import combinations
import pytest
from poker.cards import DECK
from poker.entry_chart import chart_entry,ROWS

@pytest.mark.parametrize('cards,color',[
    (['Ts','Th'],'藍色'),(['Ks','Qs'],'藍色'),(['As','Ah'],'藍色'),
    (['As','8h'],'藍色'),(['As','9h'],'灰色'),(['Ks','3s'],'黃色'),
    (['9s','5s'],'黃色'),(['9s','4s'],'灰色'),(['3s','3h'],'灰色'),
    (['3s','2s'],'黃色'),(['2s','2h'],'灰色')])
def test_supplied_chart_exact_cells_and_reversed_cards(cards,color):
    assert chart_entry(cards)['color']==color
    assert chart_entry(cards[::-1])==chart_entry(cards)
    assert chart_entry(cards)['numeric_ev'] is None

def test_all_1326_combinations_have_a_rule_and_board_disables_chart():
    assert len(ROWS)==13 and all(len(row)==13 for row in ROWS)
    for cards in combinations(DECK,2):
        assert chart_entry(cards)['color'] in ('藍色','黃色','灰色')
        assert chart_entry(cards,['4s','5s','6s'])=={}

@pytest.mark.parametrize('cards,color,label',[
    (['Ks','Qs'],'藍色','可考慮進場'),(['Ks','3s'],'黃色','看位置與下注'),
    (['7s','2h'],'灰色','不主動進場')])
def test_chart_decision_and_call_cost_are_both_visible(cards,color,label):
    from PySide6.QtWidgets import QApplication
    from ui.analysis_panel import AnalysisPanel
    from poker.starting_hands import starting_hand_guide
    app=QApplication.instance() or QApplication([])
    panel=AnalysisPanel()
    panel.render({'live':True,'street':'翻牌前','range_assumed':True,'call_amount':100,'ev':-20,
        'starting_hand':starting_hand_guide(cards)})
    assert label in panel.action_label.text()
    assert '跟注成本偏高' in panel.action_label.text()
    assert color in panel.summary.text()
    assert '使用者牌表' in panel.summary.text()
    panel.close()
