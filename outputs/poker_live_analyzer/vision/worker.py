from dataclasses import replace, asdict
import asyncio
import json
import logging
from pathlib import Path
import time
from time import perf_counter
from PySide6.QtCore import QThread, Signal
from capture.graphics_capture import GraphicsWindowCapture as WindowCapture
from vision.card_detector import StableCards
from vision.calibrated_detection import build_detectors, calibration_active
from capture.calibration import region_labels
from vision.live_state import LiveStateAssembler


class VisionWorker(QThread):
    cards = Signal(object)
    hero_view = Signal(object)
    status = Signal(str)
    timing = Signal(float)
    table = Signal(object)
    amounts = Signal(object)
    view = Signal(object)
    equity_view = Signal(object)
    unavailable = Signal(str)
    frame_received = Signal(float)

    def __init__(self, handle, parent=None, diagnostic_path=None, calibration=None):
        super().__init__(parent)
        self.handle = handle
        self.refresh_ms=100
        self.diagnostic_path = Path(diagnostic_path) if diagnostic_path else None
        self.calibration = calibration

    def _calibration_info(self, compatible=None):
        profile = self.calibration
        if profile is None:
            return {'active': False}
        return {'active': calibration_active(profile), 'locked': profile.locked,
            'positions_locked':profile.positions_locked,
            'verified': profile.verified, 'signature': profile.signature,
            'reference_size': list(profile.reference_size), 'seat_layout': profile.seat_layout,
            'regions': {name: asdict(region) for name, region in profile.regions.items()},
            'compatible': compatible}

    def _write_diagnostic(self, report):
        if not self.diagnostic_path:
            return
        try:
            self.diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.diagnostic_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(self.diagnostic_path)
        except OSError:
            pass

    def _calibration_problem(self, detection, players, amounts):
        if not calibration_active(self.calibration) or amounts.paused:
            return ''
        labels = region_labels(self.calibration.seat_layout)
        missing = [key for key in ('pot', 'hero_stack', 'call_amount') if getattr(amounts, key) is None]
        if not getattr(amounts,'core_reliable',False):
            missing.extend(f'bet_{seat}' for seat in amounts.seats if seat not in amounts.seat_bets)
        if not detection.hero_reliable:
            missing.append('hero')
        if not detection.board_reliable:
            missing.append('board')
        if missing:
            return '請校準' + '、'.join(labels.get(key, key) for key in missing) + '區域'
        if not players.reliable:
            return '請校準牌背區域：' + players.reason
        return ''

    def run(self):
        capture = None
        loop = None
        stable = StableCards(frames=3)
        last_status = None
        opened = False
        try:
            capture = WindowCapture(self.handle, protected_regions=((.04, .10, .92, .88),))
            detector, players_detector, money_detector = build_detectors(self.calibration)
            detector_signature = self.calibration.signature if calibration_active(self.calibration) else None
            assembler = LiveStateAssembler()
            loop = asyncio.new_event_loop()
            player_key, player_count = None, 0
            hero_key, hero_count = None, 0
            last_diagnostic = 0
            last_received = None
            while not self.isInterruptionRequested():
                started = perf_counter()
                frame = None
                compatible = None
                selected = None
                try:
                    if not opened:
                        capture.open()
                        opened = True
                    # 升盲與顯示單位變更時，從同一牌桌標題更新換算；不猜測盲注。
                    from capture.window_capture import list_tables
                    from vision.ocr_engine import blinds_from_title
                    selected=next((table for table in list_tables() if table.handle==self.handle),None)
                    blinds=blinds_from_title(selected.title) if selected else None
                    reader=getattr(capture,'read_sample',None)
                    if reader is not None:
                        frame,received=reader()
                    else:
                        frame=capture.read()
                        received=getattr(capture,'_received',None)
                    if self.calibration is not None and self.calibration.locked and not self.calibration.verified:
                        raise ValueError('鎖定的辨識位置已變更，請重新校準並驗證')
                    current_signature = self.calibration.signature if calibration_active(self.calibration) else None
                    if current_signature != detector_signature:
                        detector, players_detector, money_detector = build_detectors(self.calibration)
                        detector_signature = current_signature
                        stable.reset()
                        player_key, player_count = None, 0
                        hero_key, hero_count = None, 0
                        assembler.waiting()
                    if calibration_active(self.calibration):
                        compatible = False
                        self.calibration.assert_compatible((frame.shape[1], frame.shape[0]))
                        compatible = True
                    if received is not None:
                        if last_received is not None and received<=last_received:
                            self.msleep(max(20,self.refresh_ms))
                            continue
                        if time.monotonic()-received>2:
                            raise RuntimeError('牌桌影格已逾期，暫停使用舊畫面')
                        last_received=received
                    self.frame_received.emit(received if received is not None else time.monotonic())
                    money_detector.ocr.big_blind=blinds[1] if blinds else None
                    detection = detector.detect(frame)
                    current_hero = detection.hero if detection.hero_reliable and detection.hero_confidence>=.85 else None
                    hero_count = hero_count+1 if current_hero is not None and current_hero==hero_key else (1 if current_hero is not None else 0)
                    hero_key = current_hero
                    self.hero_view.emit({'hero':current_hero if hero_count>=3 else None,
                        'board':detection.board if detection.reliable and hero_count>=3 else None})
                    message = ''
                    if not detection.reliable:
                        stable.reset()
                        message = detection.reason
                    else:
                        confirmed = stable.update(detection)
                        if confirmed:
                            self.cards.emit(replace(confirmed, milliseconds=(perf_counter()-started)*1000))
                    players = players_detector.detect(frame)
                    money_detector.set_seat_layout(players_detector.seat_layout)
                    key = players.active_seats if players.reliable else None
                    player_count = player_count + 1 if key == player_key and key is not None else 1
                    player_key = key
                    amounts = loop.run_until_complete(money_detector.detect(frame))
                    if received is not None and time.monotonic()-received>2:
                        raise RuntimeError('本次辨識影格已逾期，舊建議已撤回')
                    self.amounts.emit(amounts)
                    if players.reliable and player_count >= 3:
                        self.view.emit({'amounts': amounts, 'players': players,
                            'hero_active': bool(detection.hero) if detection.reliable and stable.count>=3 else None})
                    if amounts.paused:
                        message = amounts.reason
                    elif not detection.reliable:
                        message = detection.reason
                    elif not players.reliable:
                        message = players.reason
                    elif player_count < 3 or stable.count < 3:
                        message = '正在確認牌面與持牌人數'
                    else:
                        if not detection.hero:
                            assembler.waiting()
                            message = '自身沒有可見底牌，僅顯示牌桌資訊'
                        else:
                            try:
                                self.table.emit(assembler.build(detection, players, amounts))
                            except ValueError as error:
                                message = str(error)
                    calibration_problem = self._calibration_problem(detection, players, amounts)
                    if calibration_problem:
                        message = calibration_problem
                    if (not amounts.paused and detection.reliable and detection.confidence>=.85
                            and len(detection.hero)==2 and stable.count>=3
                            and players.reliable and players.active_seats and player_count>=3):
                        self.equity_view.emit({'hero':list(detection.hero),'board':list(detection.board),
                            'active_seats':list(players.active_seats)})
                    else:
                        self.equity_view.emit(None)
                    if self.diagnostic_path and perf_counter()-last_diagnostic>=.5:
                        report={'timestamp':time.time(),'window_handle':self.handle,'window_title':selected.title if selected else '',
                            'frame_size':list(frame.shape[:2]),'cards':asdict(detection),'players':asdict(players),
                            'amounts':asdict(amounts),'message':message,'milliseconds':(perf_counter()-started)*1000,
                            'calibration': self._calibration_info(compatible)}
                        self._write_diagnostic(report)
                        last_diagnostic=perf_counter()
                    self.timing.emit((perf_counter()-started)*1000)
                except Exception as error:
                    capture.close()
                    opened = False
                    last_received = None
                    stable.reset()
                    money_detector.reset()
                    player_key, player_count = None, 0
                    message = str(error)
                    self.unavailable.emit(message)
                    self.hero_view.emit({'hero': None, 'board': None})
                    self.equity_view.emit(None)
                    if self.diagnostic_path:
                        self._write_diagnostic({'timestamp': time.time(), 'window_handle': self.handle,
                            'window_title': selected.title if selected else '',
                            'frame_size': list(frame.shape[:2]) if frame is not None else None,
                            'message': message, 'milliseconds': (perf_counter()-started)*1000,
                            'calibration': self._calibration_info(compatible)})
                    hero_key, hero_count = None, 0
                if message != last_status or message:
                    self.status.emit(message)
                    last_status = message
                remaining = max(0, self.refresh_ms-int((perf_counter()-started)*1000))
                if remaining:
                    self.msleep(remaining)
        except Exception as error:
            message=str(error)
            self.unavailable.emit(message)
            self.status.emit(message)
            self.hero_view.emit({'hero':None,'board':None})
            self.equity_view.emit(None)
            self._write_diagnostic({'timestamp':time.time(),'window_handle':self.handle,
                'frame_size':None,'message':message,'calibration':self._calibration_info(False)})
            logging.exception('即時辨識初始化或工作執行失敗')
        finally:
            for resource in (capture,loop):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception:
                        logging.exception('即時辨識資源關閉失敗')
