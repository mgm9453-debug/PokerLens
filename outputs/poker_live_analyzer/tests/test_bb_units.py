from types import SimpleNamespace
from vision.ocr_engine import NativeOcrEngine
from vision.live_state import LiveStateAssembler


def test_bb_reader_never_multiplies_by_tournament_blind():
    reader=NativeOcrEngine.__new__(NativeOcrEngine)
    reader.big_blind=2000
    reader.amount_unit='BB'
    assert reader.parse_value('底池：14.3 BB') == 14.3
    assert reader.last_resolution == .1
    assert reader.parse_value('2.50BB') == 2.5
    assert reader.last_resolution == .01
    assert reader.parse_value('2.53B') is None


def test_live_bb_rounding_keeps_real_call_and_rejects_large_difference():
    import pytest
    cards=SimpleNamespace(reliable=True,confidence=.95,hero=('As','Kh'),board=())
    players=SimpleNamespace(reliable=True,active_seats=(1,),reason='')
    amounts=SimpleNamespace(reliable=True,core_reliable=True,reason='',pot=4.2,
        hero_stack=20,call_amount=1.3,seat_bets={0:.5,1:1.9},seat_stacks={},
        seats=(0,1),field_reliable={key:True for key in ('pot','hero_stack','call_amount','bet_0','bet_1')},amount_unit='BB',
        amount_resolution={'call_amount':.1,'bet_0':.1,'bet_1':.1})
    state=LiveStateAssembler().build(cards,players,amounts)
    assert state['call_amount']==1.3
    assert state['amount_unit']=='BB' and state['big_blind']==1
    amounts.call_amount=.5
    with pytest.raises(ValueError,match='不一致'):
        LiveStateAssembler().build(cards,players,amounts)


def test_bb_format_keeps_fractions_and_marks_ev():
    from poker.amount_units import format_amount
    assert format_amount(.5)=='0.5 BB'
    assert format_amount(2.50)=='2.5 BB'
    assert format_amount(-.25,signed=True)=='-0.25 BB'


def test_legacy_conversion_is_copy_and_requires_known_blind():
    import pytest
    from poker.amount_units import state_in_bb
    old={'pot':3000,'call_amount':500,'hero_stack':10000,'big_blind':1000,
        'small_blind':500,'players':[{'stack':20000,'current_bet':1500}]}
    new=state_in_bb(old)
    assert new['pot']==3 and new['call_amount']==.5
    assert new['players'][0]['current_bet']==1.5 and new['big_blind']==1
    assert old['pot']==3000 and old['players'][0]['current_bet']==1500
    with pytest.raises(ValueError,match='缺少大盲基準'):
        state_in_bb({'pot':3000})


def test_bb_position_does_not_divide_twice_after_blind_increase():
    from tests.test_live_state import inputs
    cards,players,amounts=inputs()
    amounts.amount_unit='BB'
    amounts.hero_stack=40
    amounts.seat_stacks={seat:50 for seat in range(8)}
    amounts.seat_bets={seat:0 for seat in range(8)}
    amounts.field_reliable={key:True for key in ['hero_stack',*[f'stack_{seat}' for seat in range(8)],*[f'bet_{seat}' for seat in range(8)]]}
    assembler=LiveStateAssembler()
    first=assembler.observe_position(cards,players,amounts,5,(1000,2000))
    second=assembler.observe_position(cards,players,amounts,5,(2000,4000))
    assert first['stack_bb']==second['stack_bb']==40
    assert first['scenario']==second['scenario']=='open'
    assert assembler.blinds==(.5,1)


def test_bb_precision_cannot_accept_obviously_broken_pot():
    import pytest
    from state.models import PokerTableState
    state={'amount_unit':'BB','big_blind':1,'pot':2.4,'players':[{'seat':0,'current_bet':1.2},{'seat':1,'current_bet':1.3}],
        'amount_resolution':{'pot':.1,'bet_0':.1,'bet_1':.1}}
    PokerTableState.from_dict(state)
    state['pot']=1
    with pytest.raises(ValueError,match='底池不可小於'):
        PokerTableState.from_dict(state)
    state['amount_resolution']['pot']=float('nan')
    with pytest.raises(ValueError,match='精度'):
        PokerTableState.from_dict(state)


def test_bb_action_and_overlay_show_fractional_call():
    from PySide6.QtWidgets import QApplication
    from ui.analysis_panel import AnalysisPanel
    from ui.table_overlay import TableOverlay
    app=QApplication.instance() or QApplication([])
    result={'live':True,'amount_unit':'BB','hero_turn':True,'hero_cards':['As','Kh'],
        'community_cards':[],'pot':4,'call_amount':.5,'ev':1,'equity':.6,
        'simulation_count':50000,'range_assumed':True,
        'equity_details':{'win_probability':.6}}
    panel=AnalysisPanel()
    panel.render(result)
    assert '0.5 BB' in panel.action_label.text()
    assert '0.5 BB' in panel.sizing_label.text() and '12.5%' in panel.sizing_label.text()
    overlay=TableOverlay()
    overlay.render(result,result)
    assert '0.5 BB' in overlay.details.text() and '4 BB' in overlay.details.text()
    panel.close();overlay.close()


def test_bb_rounding_boundary_does_not_force_a_call():
    from PySide6.QtWidgets import QApplication
    from ui.analysis_panel import AnalysisPanel
    app=QApplication.instance() or QApplication([])
    panel=AnalysisPanel()
    panel.render({'live':True,'amount_unit':'BB','hero_turn':True,
        'hero_cards':['As','Kh'],'community_cards':[],'pot':4,'call_amount':1,
        'ev':.15,'equity':.23,'simulation_count':1000000,
        'amount_rounding_ev_bound':.2,'range_assumed':True})
    assert '跟注 1 BB' not in panel.action_label.text()
    assert '確認' in panel.action_label.text()
    panel.close()


def test_bb_table_detector_tracks_units_precision_and_missing_unit_evidence():
    import asyncio
    import numpy as np
    from vision.table_detector import TableDetector
    from vision.ocr_engine import OcrText
    reader=NativeOcrEngine.__new__(NativeOcrEngine)
    reader.amount_unit='BB';reader.big_blind=2000;reader.bb_display=False
    reader.last_resolution=0
    counter=[0];has_unit=[True]
    async def read(image):
        counter[0]+=1
        reader.last_resolution=.1
        reader.bb_display=has_unit[0]
        return 20 if counter[0]==1 else 40 if counter[0]==2 or counter[0]>11 else 0
    async def recognize(image): return OcrText('',True)
    reader.read_amount=reader.read_pot_amount=read
    reader.recognize=recognize
    detector=TableDetector(stable_frames=2,ocr=reader)
    frame=np.full((805,1134,3),70,dtype=np.uint8)
    async def detect():
        counter[0]=0
        return await detector.detect(frame)
    asyncio.run(detect())
    amounts=asyncio.run(detect())
    assert amounts.amount_unit=='BB' and amounts.pot==20
    assert amounts.amount_resolution['pot']==.1 and amounts.core_reliable
    has_unit[0]=False
    amounts=asyncio.run(detect())
    assert not amounts.reliable and not amounts.core_reliable
    assert '大盲數顯示' in amounts.reason


def test_engine_preserves_bb_scale_equity_and_rounding_bound():
    import pytest
    from unittest.mock import patch
    from poker.engine import AnalysisEngine
    from poker.equity import EquityResult
    from state.models import PokerTableState
    from poker.amount_units import state_in_bb
    old=PokerTableState(hero_cards=['As','Kh'],hero_seat=0,players=[{'seat':0,'stack':5000},{'seat':1,'stack':5000,'current_bet':500}],pot=2000,call_amount=500,hero_stack=5000,effective_stack=5000,big_blind=100)
    new=PokerTableState.from_dict(state_in_bb(old.to_dict()))
    new.amount_resolution={'pot':.1,'call_amount':.1}
    engine=AnalysisEngine(10000)
    cache=(engine.equity_key(old),EquityResult(.6,.4,.02,.58,10000))
    with patch('poker.engine.calculate_equity',side_effect=AssertionError('不應重抽牌')):
        first=engine.analyze(old,cached_equity=cache)
        second=engine.analyze(new,cached_equity=cache)
    assert second.equity==first.equity and second.required_equity==first.required_equity
    assert second.ev==pytest.approx(first.ev/100)
    assert second.amount_unit=='BB' and second.amount_rounding_ev_bound==pytest.approx(.05)


def test_bb_empty_seat_does_not_create_calibration_error():
    from vision.calibrated_detection import omit_inactive_seat_errors
    assert omit_inactive_seat_errors({'back_2':'已確認無牌背','bet_2':'0 BB'},{'stack_2':'讀不到'})=={}


def test_native_bb_text_reads_fraction_without_chip_conversion():
    import sys
    import pytest
    if sys.platform!='win32': pytest.skip('需要原生文字辨識')
    import asyncio
    import cv2
    import numpy as np
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    reader=NativeOcrEngine(big_blind=2000)
    reader.amount_unit='BB'
    image=np.full((40,200,3),30,np.uint8)
    cv2.putText(image,'14.3 BB',(8,29),cv2.FONT_HERSHEY_SIMPLEX,.8,(240,240,240),2,cv2.LINE_AA)
    assert asyncio.run(reader.read_amount(image))==14.3
    assert reader.bb_display and reader.last_resolution==.1
