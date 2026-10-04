from dataclasses import replace, asdict
import asyncio
import json
from pathlib import Path
import time
from time import perf_counter
from PySide6.QtCore import QThread, Signal
from capture.graphics_capture import GraphicsWindowCapture as WindowCapture
from vision.card_detector import CardDetector, StableCards
from vision.player_detector import PlayerDetector
from vision.table_detector import TableDetector
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

    def __init__(self, handle, parent=None, diagnostic_path=None):
        super().__init__(parent)
        self.handle = handle
        self.refresh_ms=100
        self.diagnostic_path = Path(diagnostic_path) if diagnostic_path else None

    def run(self):
        capture = WindowCapture(self.handle, protected_regions=((.04, .10, .92, .88),))
        stable = StableCards(frames=3)
        last_status = None
        opened = False
        detector = CardDetector()
        players_detector = PlayerDetector(green_only=True)
        money_detector = TableDetector()
        assembler = LiveStateAssembler()
        loop = asyncio.new_event_loop()
        player_key, player_count = None, 0
        hero_key, hero_count = None, 0
        last_diagnostic = 0
        try:
            while not self.isInterruptionRequested():
                started = perf_counter()
                try:
                    if not opened:
                        capture.open()
                        opened = True
                    # 升盲與顯示單位變更時，從同一牌桌標題更新換算；不猜測盲注。
                    from capture.window_capture import list_tables
                    from vision.ocr_engine import blinds_from_title
                    selected=next((table for table in list_tables() if table.handle==self.handle),None)
                    blinds=blinds_from_title(selected.title) if selected else None
                    money_detector.ocr.big_blind=blinds[1] if blinds else None
                    frame = capture.read()
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
                    key = players.active_seats if players.reliable else None
                    player_count = player_count + 1 if key == player_key and key is not None else 1
                    player_key = key
                    amounts = loop.run_until_complete(money_detector.detect(frame))
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
                            'amounts':asdict(amounts),'message':message,'milliseconds':(perf_counter()-started)*1000}
                        try:
                            self.diagnostic_path.parent.mkdir(parents=True,exist_ok=True)
                            temporary=self.diagnostic_path.with_suffix('.tmp')
                            temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                            temporary.replace(self.diagnostic_path)
                        except OSError:
                            pass
                        last_diagnostic=perf_counter()
                    self.timing.emit((perf_counter()-started)*1000)
                except Exception as error:
                    capture.close()
                    opened = False
                    stable.reset()
                    money_detector.reset()
                    player_key, player_count = None, 0
                    message = str(error)
                    self.unavailable.emit(message)
                    hero_key, hero_count = None, 0
                if message != last_status or message:
                    self.status.emit(message)
                    last_status = message
                remaining = max(0, self.refresh_ms-int((perf_counter()-started)*1000))
                if remaining:
                    self.msleep(remaining)
        finally:
            capture.close()
            loop.close()
