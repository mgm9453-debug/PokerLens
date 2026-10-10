from poker.equity import calculate_equity


def test_time_budget_returns_completed_samples_without_marking_cancelled(monkeypatch):
    import poker.equity as module
    clock=iter([0,1,2,3,4,5])
    monkeypatch.setattr(module,'perf_counter',lambda:next(clock))
    result=calculate_equity(['As','Kd'],[],['standard'],2000,time_budget=.25)
    assert 128<=result.iterations_completed<2000
    assert not result.cancelled
    assert 0<=result.hero_equity<=1


def test_time_budget_does_not_override_cancellation():
    result=calculate_equity(['As','Kd'],[],['standard'],2000,cancel=lambda:True,time_budget=.25)
    assert result.cancelled and result.iterations_completed==0


def test_normal_analysis_still_finishes_requested_samples():
    result=calculate_equity(['As','Kd'],[],['standard'],2000)
    assert result.iterations_completed==2000 and not result.cancelled


def test_full_analysis_does_not_launch_duplicate_equity_preview(tmp_path):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from time import monotonic
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow,AnalysisWorker,demo_data
    from state.models import PokerTableState
    app=QApplication.instance() or QApplication([])
    window=MainWindow(data_dir=tmp_path,auto_demo=False)
    window.auto_active=True
    window.capture_last_frame=monotonic()
    state=PokerTableState.from_dict(demo_data())
    window.detector.state=state
    worker=AnalysisWorker(1,state,2000,42,window)
    window.workers.append(worker)
    try:
        window.accept_equity_view(window.auto_generation,{'hero':state.hero_cards,'board':state.board,'active_seats':[2]})
        assert window.workers==[worker]
    finally:
        window.workers.remove(worker)
        worker.deleteLater()
        window.close();app.processEvents()


def test_precomputed_equity_only_reused_for_same_active_opponents(tmp_path,monkeypatch):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    import ui.main_window as module
    from state.models import PokerTableState
    app=QApplication.instance() or QApplication([])
    window=module.MainWindow(data_dir=tmp_path,auto_demo=False)
    window.auto_active=True
    state=PokerTableState.from_dict(module.demo_data())
    state.ranges={'2':window.control_options['opponent_range']}
    window.detector.state=state
    captured=[]
    class Worker(module.AnalysisWorker):
        def start(self):captured.append(self.cached_equity)
    monkeypatch.setattr(module,'AnalysisWorker',Worker)
    window.partial_equity_key=(window.auto_generation,tuple(state.hero_cards),tuple(state.board),(2,),window.control_options['opponent_range'])
    window.partial_equity_result={'equity_details':{'hero_equity':.6,'opponents_equity':.4,'tie_probability':0,'win_probability':.6,'iterations_completed':320}}
    try:
        window.start_analysis()
        assert captured[-1] is not None
        window.partial_equity_key=(*window.partial_equity_key[:3],(2,3),window.partial_equity_key[-1])
        window.start_analysis()
        assert captured[-1] is None
    finally:
        window.close();app.processEvents()
