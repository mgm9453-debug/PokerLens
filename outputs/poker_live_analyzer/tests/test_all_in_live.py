import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import asyncio,sys
from pathlib import Path
import cv2,numpy as np,pytest
from PySide6.QtWidgets import QApplication

@pytest.mark.skipif(sys.platform!='win32',reason='需要原生文字辨識')
def test_screenshot_call_and_all_in_use_current_amounts():
    from vision.table_detector import TableDetector
    from vision.live_state import LiveStateAssembler
    from vision.card_detector import Detection
    from vision.player_detector import PlayerDetection
    app=QApplication.instance() or QApplication([])
    frame=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/all_in_amounts_anonymous.png',np.uint8),1)
    async def run():
        detector=TableDetector()
        for _ in range(3):result=await detector.detect(frame)
        return result
    amounts=asyncio.run(run())
    assert amounts.reliable,amounts.reason
    assert amounts.call_amount==5180
    assert amounts.pot==6860
    assert amounts.all_in_seats==(3,)
    state=LiveStateAssembler().build(Detection(('Ks','8s'),(),.95,True),PlayerDetection((1,3),True),amounts)
    assert next(player for player in state['players'] if player['seat']==3)['all_in']


def test_changed_call_clears_old_recommendation_before_stability(tmp_path):
    from ui.main_window import MainWindow
    from state.models import PokerTableState
    from vision.table_detector import TableAmounts
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.auto_active=True
    window.detector.state=PokerTableState(hero_cards=['Ks','8s'],hero_seat=0,pot=1380,
        call_amount=300,hero_stack=5360,players=[{'seat':0,'current_bet':300},{'seat':1,'current_bet':600}])
    window.result={'live':True,'call_amount':300}
    generation=window.generation
    try:
        window.accept_auto_amounts(window.auto_generation,TableAmounts(6860,5360,5180,
            {0:300,1:600,3:5480},False,'等待連續多幀金額一致',0))
        assert window.result is None
        assert window.generation>generation
        assert '舊建議已撤回' in window.analysis.issue_label.text()
        assert '等待資料確認' in window.analysis.action_label.text()
    finally:window.close()
