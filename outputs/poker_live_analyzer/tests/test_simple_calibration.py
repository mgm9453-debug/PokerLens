import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from capture.calibration import CalibrationProfile,CalibrationStore,default_regions
from vision.calibrated_detection import calibration_active


def test_position_lock_is_separate_from_successful_reading(tmp_path):
    profile=CalibrationProfile(default_regions(),(1128,799)).lock_positions()
    assert profile.positions_locked and not profile.verified
    assert calibration_active(profile)
    store=CalibrationStore(tmp_path/'positions.json');store.save(profile)
    restored=store.load()
    assert restored.positions_locked and not restored.verified
    restored.regions['pot']=restored.regions['hero']
    assert not calibration_active(restored)
    with pytest.raises(ValueError):store.save(restored)


def test_unlock_allows_position_changes_without_old_success_status():
    profile=CalibrationProfile(default_regions(),(1128,799)).lock_positions()
    assert not profile.unlock().positions_locked
    assert not profile.with_region('pot',profile.regions['hero']).positions_locked


def test_one_button_populates_every_information_box(tmp_path):
    from ui.calibration_dialog import CalibrationDialog
    app=QApplication.instance() or QApplication([])
    dialog=CalibrationDialog(tmp_path/'positions.json',lambda:None,table_provider=lambda:[])
    dialog.canvas.set_frame(np.ones((799,1128,3),dtype=np.uint8)*40)
    try:
        dialog.show_all_positions()
        assert set(dialog.profile.regions)==set(default_regions(dialog.profile.seat_layout))
        assert '未鎖定' in dialog.position_status.text()
    finally:dialog.close();app.processEvents()


def test_one_click_lock_keeps_position_lock_and_reports_unresolved_reading(tmp_path,monkeypatch):
    from ui.calibration_dialog import CalibrationDialog
    from vision.calibrated_detection import CalibrationValidation
    app=QApplication.instance() or QApplication([])
    saved=[]
    path=tmp_path/'positions.json'
    dialog=CalibrationDialog(path,lambda:saved.append(True),table_provider=lambda:[])
    dialog.table_combo.blockSignals(True)
    dialog.table_combo.addItem('測試牌桌',11)
    dialog.table_combo.blockSignals(False)
    dialog.canvas.set_frame(np.ones((799,1128,3),dtype=np.uint8)*40)
    monkeypatch.setattr(dialog,'_start_worker',lambda profile:None)
    try:
        dialog.show_all_positions()
        dialog.lock_positions_and_check()
        assert saved and CalibrationStore(path).load().positions_locked
        assert dialog.canvas.locked
        dialog._accept_validation(dialog._generation,CalibrationValidation(False,{'pot':'1000'},{'call_amount':'尚未輪到自己，跟注金額尚未出現'},dialog.profile.signature))
        assert '仍有 1 項未確認' in dialog.check_status.text()
        assert '尚未全部排除' in dialog.status.text()
        assert dialog.profile.positions_locked and not dialog.profile.verified
        dialog.unlock()
        assert not dialog.canvas.locked and '未鎖定' in dialog.position_status.text()
    finally:dialog.close();app.processEvents()


def test_clicking_information_box_selects_it_and_locked_box_cannot_change():
    from ui.calibration_dialog import CalibrationCanvas
    from capture.profiles import Region,TableProfile
    from PySide6.QtCore import QPoint,Qt
    from PySide6.QtTest import QTest
    app=QApplication.instance() or QApplication([])
    canvas=CalibrationCanvas();canvas.resize(900,650)
    canvas.set_frame(np.ones((799,1128,3),dtype=np.uint8)*40)
    canvas.profile=TableProfile({'pot':Region(.1,.1,.1,.1)})
    canvas.target='hero';canvas.show();app.processEvents()
    rect=canvas.image_rect();point=QPoint(round(rect.x()+.15*rect.width()),round(rect.y()+.15*rect.height()))
    try:
        QTest.mouseClick(canvas,Qt.LeftButton,pos=point)
        assert canvas.target=='pot'
        canvas.target='hero';canvas.locked=True
        QTest.mouseClick(canvas,Qt.LeftButton,pos=point)
        assert canvas.target=='hero'
    finally:canvas.close();app.processEvents()


def test_redrawing_selected_box_does_not_switch_to_overlapping_information():
    from ui.calibration_dialog import CalibrationCanvas
    from capture.profiles import Region,TableProfile
    from PySide6.QtCore import QPoint,Qt
    from PySide6.QtTest import QTest
    app=QApplication.instance() or QApplication([])
    canvas=CalibrationCanvas();canvas.resize(900,650)
    board=Region(.3,.1,.1,.1)
    canvas.profile=TableProfile({'pot':Region(.1,.1,.1,.1),'board':board})
    canvas.set_frame(np.ones((799,1128,3),dtype=np.uint8)*40)
    canvas.target='pot';canvas.show();app.processEvents()
    rect=canvas.image_rect()
    first=QPoint(round(rect.x()+.31*rect.width()),round(rect.y()+.11*rect.height()))
    last=QPoint(round(rect.x()+.48*rect.width()),round(rect.y()+.25*rect.height()))
    try:
        QTest.mousePress(canvas,Qt.LeftButton,pos=first)
        QTest.mouseMove(canvas,last)
        QTest.mouseRelease(canvas,Qt.LeftButton,pos=last)
        assert canvas.target=='pot' and canvas.profile.regions['board']==board
        assert canvas.profile.regions['pot'].x==pytest.approx(.31,abs=.005)
    finally:canvas.close();app.processEvents()
