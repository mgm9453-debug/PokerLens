import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from ui.calibration_dialog import CalibrationDialog

def test_only_unread_fields_are_shown(tmp_path):
    app=QApplication.instance() or QApplication([])
    dialog=CalibrationDialog(tmp_path/'位置.json',lambda:None,table_provider=lambda:[])
    try:
        import numpy as np
        dialog.canvas.set_frame(np.ones((799,1128,3),dtype=np.uint8)*40)
        dialog.show_all_positions()
        dialog._render_results({'pot':'1000'},{'call_amount':'跟注金額尚未讀到'})
        assert dialog.results.rowCount()==1
        assert dialog.canvas.visible_fields==set()
        dialog.results.selectRow(0)
        assert dialog.canvas.visible_fields=={'call_amount'}
    finally:dialog.close();app.processEvents()

def test_optional_seat_without_cards_and_bet_is_not_a_calibration_error():
    from vision.calibrated_detection import omit_inactive_seat_errors
    readings={'back_3':'已確認無牌背','bet_3':'0'}
    errors={'stack_3':'沒有金額','stack_4':'未讀到'}
    assert omit_inactive_seat_errors(readings,errors)=={'stack_4':'未讀到'}
