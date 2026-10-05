import json
import logging
from time import monotonic
from pathlib import Path
from threading import Event
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QComboBox, QSpinBox, QPlainTextEdit, QSplitter, QTabWidget, QListWidget,
    QCheckBox, QSlider, QApplication, QMessageBox, QFileDialog, QScrollArea, QInputDialog)
from capture.worker import CaptureWorker
from capture.screen_capture import ScreenCapture
from capture.obs_capture import ObsCapture
from capture.profiles import TableProfile
from ui.roi_editor import RoiEditor
from ui.analysis_panel import AnalysisPanel
from ui.table_overlay import TableOverlay
from ui.settings import AnalysisSettings
from ui.simple_form import SimpleHandForm
from state.table_state import PokerTableState
from state.state_detector import StateDetector
from database.database import StateRepository
from poker.engine import AnalysisEngine
from poker.equity import EquityResult
from poker.evaluator import evaluate_hand
from capture.window_capture import list_tables
from vision.worker import VisionWorker


def demo_data():
    return {
        'hero_cards': ['As', 'Ks'], 'community_cards': ['Ah', '8s', '3s'],
        'hero_seat': 1, 'pot': 2000, 'call_amount': 800,
        'hero_stack': 8000, 'effective_stack': 8000,
        'small_blind': 50, 'big_blind': 100, 'dealer_position': 2,
        'players': [
            {'seat': 1, 'position': '大盲', 'stack': 8000, 'current_bet': 0,
             'total_invested': 100, 'action': '等待', 'folded': False, 'confidence': {}},
            {'seat': 2, 'position': '莊家', 'stack': 8000, 'current_bet': 800,
             'total_invested': 900, 'action': '下注', 'folded': False, 'confidence': {}}],
        'ranges': {'2': 'standard'}, 'street': ''
    }


def editable_state(data):
    """只顯示主要欄位，避免相同資料的相容別名混淆手動編輯。"""
    data = json.loads(json.dumps(data, ensure_ascii=False))
    data.pop('board', None)
    data.pop('dealer_seat', None)
    for player in data.get('players', []):
        player.pop('bet', None)
    return data


class AnalysisWorker(QThread):
    succeeded = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, version, state, iterations, seed, parent=None, cached_equity=None):
        super().__init__(parent)
        self.version, self.state = version, state
        self.iterations, self.seed = iterations, seed
        self.cancel = Event()
        self.cached_equity = cached_equity

    def run(self):
        try:
            result = AnalysisEngine(iterations=self.iterations, seed=self.seed).analyze(self.state, cancel=self.cancel.is_set, cached_equity=self.cached_equity)
            if not self.cancel.is_set():
                self.succeeded.emit(self.version, result)
        except Exception as error:
            if not self.cancel.is_set():
                self.failed.emit(self.version, str(error))


class MainWindow(QMainWindow):
    def __init__(self, data_dir=None, auto_demo=True):
        super().__init__()
        from .fonts import interface_font
        self.setFont(interface_font())
        from version import APP_NAME
        self.setWindowTitle(APP_NAME)
        self.resize(780, 960)
        self.setMinimumSize(640,900)
        self.setWindowFlag(Qt.WindowMinimizeButtonHint,False)
        from app_paths import user_data_dir
        self.data_dir = Path(data_dir) if data_dir is not None else user_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        from control_settings import read,validate
        self.control_path=self.data_dir/'control_settings.json'
        try: self.control_options=read(self.control_path)
        except (ValueError,OSError): self.control_options=validate({})
        # 保留模式與數值；新工作階段必須重新確認當前牌桌規則。
        self.control_options.update(bounty_active=False,bounty_known=False,rake_known=False)
        if self.control_path.exists():
            from control_settings import write
            try: write(self.control_options,self.control_path)
            except OSError: pass
        self.capture_last_frame=0.0
        self.capture_title='尚未選定牌桌'
        self.profile_dir = self.data_dir / 'profiles'
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.detector = StateDetector()
        self.repository = StateRepository(self.data_dir / 'history.sqlite3')
        stored_events = self.repository.list_events()
        if stored_events:
            self.detector.version = max(event['version'] for event in stored_events)
        self.capture_worker = None
        self.vision_worker = None
        self.dock_key=None
        self.floating_mode=False
        self.auto_active = False
        self.auto_waiting = False
        self.auto_watch = False
        self.auto_monitor = QTimer(self)
        self.auto_monitor.setInterval(1500)
        self.auto_monitor.timeout.connect(self.monitor_auto)
        self.auto_generation = 0
        self.auto_category = None
        self.equity_cache = None
        self.card_threat_key=None
        self.card_threat_result=None
        self.partial_equity_key=None
        self.partial_equity_result=None
        self.partial_equity_time=0.0
        self.last_hero_names=''
        self.last_hero_time=0.0
        self.live_numbers = QLabel('等待牌桌資料')
        self.live_numbers.setWordWrap(True)
        self.live_numbers.setStyleSheet('font-size: 18px; padding: 8px; background: #edf5fa;')
        self.live_cards = QLabel('底牌：等待辨識')
        self.live_cards.setWordWrap(True)
        self.live_cards.setStyleSheet('font-size: 18px; padding: 8px; background: #eef8f0;')
        self.workers = []
        self.result = None
        self.generation = 0
        self.uncertain = False
        self.replay_mode = False
        self.simple_dirty = False
        self.overlay = TableOverlay()
        self.overlay.open_main.connect(self.restore_main)
        from ui.theme import STYLE
        self.setStyleSheet(STYLE)
        from .reference_style import ReferenceSurface
        central = ReferenceSurface()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(34,14,34,18)
        title = QLabel('<span style="color:#FFFFFF;font-size:30px;font-weight:600;">Poker</span><span style="color:#EFC67A;font-size:30px;font-weight:600;">Lens</span><span style="color:#EFC67A;"> │ </span><span style="color:#FFFFFF;font-size:19px;">牌局分析</span>')
        title.setStyleSheet('font-size: 20px; font-weight:500; color: #F4DCA4; padding:8px;')
        title_row=QHBoxLayout()
        title_row.addStretch()
        self.floating_button=QPushButton('收合到懸浮窗')
        self.floating_button.clicked.connect(self.show_floating)
        title_row.addWidget(self.floating_button)
        self.control_button=QPushButton('調整設定')
        self.control_button.clicked.connect(self.open_control_settings)
        title_row.addWidget(self.control_button)
        title_header=QWidget()
        title_header.setStyleSheet("background:transparent;")
        title_header_layout=QVBoxLayout(title_header)
        title_header_layout.setContentsMargins(8,0,8,0)
        title_header_layout.setSpacing(0)
        title_header.setStyleSheet("background:transparent; QPushButton {font-size:13px;padding:6px 10px;}")
        title_header_layout.addWidget(title)
        title_header_layout.addLayout(title_row)
        layout.addWidget(title_header)
        self.table_controls=QWidget(central)
        table_row=QHBoxLayout(self.table_controls)
        table_row.addWidget(QLabel('追蹤牌桌'))
        self.table_choice=QComboBox()
        self.table_choice.addItem('自動選擇可用牌桌',None)
        self.table_choice.setMinimumWidth(280)
        table_row.addWidget(self.table_choice,1)
        refresh=QPushButton('重新找牌桌')
        refresh.clicked.connect(self.refresh_table_choices)
        table_row.addWidget(refresh)
        self.table_choice.activated.connect(self.change_table)
        self.table_controls.hide()
        guide = QLabel('即時模式自動讀取牌桌並更新分析；不需要按「分析」。')
        guide.setStyleSheet('color: #FFFFFF;')
        self.guide=guide
        layout.addWidget(guide)
        self.amount_unit_notice=QLabel()
        self.amount_unit_notice.setWordWrap(True)
        self.amount_unit_notice.setStyleSheet('font-size:18px;color:#ffc66d;padding:8px;')
        self.amount_unit_notice.hide()
        layout.addWidget(self.amount_unit_notice)
        layout.addWidget(self.live_numbers)
        layout.addWidget(self.live_cards)
        self.mode_label = QLabel('示範牌局：可直接按分析，或換成你的牌與金額。')
        self.mode_label.setStyleSheet('color: #FFFFFF; padding-bottom: 8px;')
        layout.addWidget(self.mode_label)
        simple_split = QSplitter()
        self.simple_form = SimpleHandForm()
        self.simple_form.load_data(demo_data())
        self.simple_form.edited.connect(self.form_edited)
        self.analysis = AnalysisPanel()
        self.analysis.dark_theme=True
        self.analysis.enable_fixed_layout()
        self.analysis.layout().removeWidget(self.analysis.card_strip)
        self.analysis.card_strip.setParent(self.analysis.details)
        self.analysis.card_strip.hide()
        self.analysis.details_toggle.hide()
        self.analysis.details.hide()
        self.statusBar().hide()
        layout.removeWidget(self.live_numbers)
        layout.removeWidget(self.live_cards)
        self.live_cards.hide()
        self.live_cards.deleteLater()
        self.live_cards=self.analysis.card_text
        self.live_numbers.hide()
        self.live_cards.setStyleSheet('font-size:17px;padding:10px;color:#d9e8f4;background:#132839;border-radius:8px;')
        self.live_numbers.setStyleSheet('font-size:16px;padding:10px;color:#b9d1e1;background:#152c3e;border-radius:8px;')
        simple_split.addWidget(self.simple_form)
        simple_split.addWidget(self.analysis)
        simple_split.setSizes([440, 620])
        layout.addWidget(simple_split, 1)
        main_buttons = QHBoxLayout()
        self.analyze_button = self.add_button(main_buttons, '③ 分析', self.analyze_simple)
        self.analyze_button.setMinimumHeight(46)
        self.analyze_button.setStyleSheet('font-size: 18px; font-weight: bold; color: white; background: #167d65; border-radius: 8px; padding: 8px 30px;')
        self.clear_button = self.add_button(main_buttons, '清空', self.clear_simple)
        self.demo_button = self.add_button(main_buttons, '載入示範', self.load_demo)
        self.auto_button = self.add_button(main_buttons, '開始自動辨識', self.toggle_auto)
        self.auto_button.setMinimumHeight(40)
        main_buttons.removeWidget(self.auto_button)
        title_row.insertWidget(1,self.auto_button)
        layout.addLayout(main_buttons)
        self.auto_status = QLabel('自動辨識尚未啟動')
        self.auto_status.setStyleSheet('color: #167d65;')
        layout.addWidget(self.auto_status)
        self.advanced_toggle = QCheckBox('進階設定：畫面擷取、對手範圍、歷史與完整資料')
        layout.addWidget(self.advanced_toggle)
        self.advanced = QWidget()
        advanced_layout = QVBoxLayout(self.advanced)
        self.advanced_scroll = QScrollArea()
        self.advanced_scroll.setWidgetResizable(True)
        self.advanced_scroll.setWidget(self.advanced)
        self.advanced_scroll.setMaximumHeight(300)
        self.advanced_scroll.setVisible(False)
        self.advanced_toggle.toggled.connect(self.advanced_scroll.setVisible)
        layout.addWidget(self.advanced_scroll)
        toolbar = QHBoxLayout()
        self.source = QComboBox()
        self.source.addItems(['螢幕擷取', '虛擬攝影機'])
        self.source_index = QSpinBox()
        self.source_index.setRange(0, 20)
        self.source_index.setValue(1)
        self.source.currentIndexChanged.connect(lambda index: self.source_index.setValue(0 if index else 1))
        toolbar.addWidget(self.source)
        toolbar.addWidget(QLabel('螢幕／攝影機編號'))
        toolbar.addWidget(self.source_index)
        self.add_button(toolbar, '開始擷取', self.start_capture)
        self.add_button(toolbar, '停止擷取', self.stop_capture)
        self.region = QComboBox()
        self.region.addItems(['牌桌', '底牌', '公共牌', '底池'] + [f'玩家 {i}' for i in range(1, 10)])
        toolbar.addWidget(self.region)
        self.add_button(toolbar, '儲存區域', self.save_profile)
        self.add_button(toolbar, '載入區域', self.load_profile)
        advanced_layout.addLayout(toolbar)
        self.view = RoiEditor()
        self.region.currentTextChanged.connect(lambda text: setattr(self.view, 'target', text))
        self.view.selected.connect(lambda name: self.statusBar().showMessage(f'已設定{name}區域'))
        self.view.setMinimumHeight(160)
        advanced_layout.addWidget(self.view, 1)
        self.settings = AnalysisSettings()
        advanced_layout.addWidget(self.settings)
        self.settings.iterations.currentIndexChanged.connect(self.recalculate)
        self.settings.seed.valueChanged.connect(self.recalculate)
        self.settings.fold.valueChanged.connect(self.update_fold)
        tabs = QTabWidget()
        manual = QWidget()
        manual_layout = QVBoxLayout(manual)
        manual_layout.addWidget(QLabel('資料來源：假資料／手動輸入。畫面擷取尚未接入辨識。\n下方可編輯所有牌局欄位；底池包含已投入下注，跟注額是新增投入。'))
        self.editor = QPlainTextEdit()
        self.editor.setPlainText(json.dumps(demo_data(), ensure_ascii=False, indent=2))
        manual_layout.addWidget(self.editor)
        buttons = QHBoxLayout()
        self.add_button(buttons, '套用手動資料', self.apply_editor)
        self.add_button(buttons, '載入假資料', self.load_demo)
        self.add_button(buttons, '示範下注變化', self.demo_change)
        manual_layout.addLayout(buttons)
        self.current = QLabel('尚未建立牌局')
        self.current.setWordWrap(True)
        manual_layout.addWidget(self.current)
        tabs.addTab(manual, '牌局資料')
        ranges = QWidget()
        range_layout = QVBoxLayout(ranges)
        range_layout.addWidget(QLabel('自訂範圍以牌型空格分隔，例如 AA KK AKs AKo。\n範圍名稱：緊、標準、寬；自訂範圍套用於所有未棄牌對手。'))
        self.range_choice = QComboBox()
        self.range_choice.addItems(['緊', '標準', '寬', '自訂'])
        self.range_choice.setCurrentIndex(1)
        range_layout.addWidget(self.range_choice)
        self.range_text = QPlainTextEdit('AA KK QQ JJ TT AK AQ AJ KQ')
        range_layout.addWidget(self.range_text)
        self.add_button(range_layout, '套用對手範圍', self.apply_range)
        self.add_button(range_layout, '儲存範圍', self.save_range)
        self.add_button(range_layout, '載入範圍', self.load_range)
        tabs.addTab(ranges, '對手範圍')
        self.history = QListWidget()
        self.history.itemClicked.connect(self.replay)
        history_widget = QWidget()
        history_layout = QVBoxLayout(history_widget)
        history_layout.addWidget(QLabel('點選紀錄回放當時狀態及已完成的分析。'))
        history_layout.addWidget(self.history)
        self.add_button(history_layout, '返回目前牌局', self.return_live)
        tabs.addTab(history_widget, '歷史回放')
        advanced_layout.addWidget(tabs, 1)
        overlay_bar = QHBoxLayout()
        show = QCheckBox('顯示浮窗')
        show.toggled.connect(self.overlay.setVisible)
        pin = QCheckBox('浮窗置頂')
        pin.setChecked(True)
        pin.toggled.connect(self.overlay.set_pinned)
        opacity = QSlider(Qt.Orientation.Horizontal)
        opacity.setRange(25, 100)
        opacity.setValue(95)
        opacity.valueChanged.connect(lambda value: self.overlay.setWindowOpacity(value/100))
        overlay_bar.addWidget(show)
        overlay_bar.addWidget(pin)
        overlay_bar.addWidget(QLabel('浮窗透明度'))
        overlay_bar.addWidget(opacity)
        advanced_layout.addLayout(overlay_bar)
        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.poll_frame)
        self.frame_timer.start(33)
        self.refresh_history()
        self.statusBar().showMessage('就緒：此階段使用假資料與手動輸入')
        self.analysis.apply_display_options(self.control_options)
        self.live_numbers.hide()
        self.control_timer=QTimer(self)
        self.control_timer.timeout.connect(self.poll_control_settings)
        self.control_timer.start(1000)
        if self.control_path.exists():
            self.settings.iterations.blockSignals(True)
            self.settings.iterations.setCurrentIndex(self.settings.iterations.findData(self.control_options['iterations']))
            self.settings.iterations.blockSignals(False)
        # 小螢幕側邊顯示時可垂直捲動，避免內容最小尺寸把視窗撐回牌桌上。
        body=self.takeCentralWidget()
        self.main_scroll=QScrollArea()
        self.main_scroll.setWidgetResizable(True)
        self.main_scroll.setWidget(body)
        self.setCentralWidget(self.main_scroll)
        if auto_demo:
            QTimer.singleShot(0,self.apply_editor)
        try: self.refresh_table_choices()
        except (OSError,RuntimeError): pass

    def open_control_settings(self):
        from ui.control_dialog import ControlDialog
        dialog=ControlDialog(self.control_options,self.save_control_settings,self.capture_status,self,
                             update_controller=getattr(self,'update_controller',None))
        dialog.exec()

    def show_floating(self):
        self.floating_mode=True
        self.overlay.adjustSize()
        area=self.screen().availableGeometry()
        position=self.overlay.pos()
        self.overlay.move(max(area.left(),min(position.x(),area.right()-self.overlay.width()+1)),
                          max(area.top(),min(position.y(),area.bottom()-self.overlay.height()+1)))
        self.overlay.show()
        self.overlay.raise_()
        self.hide()
        logging.info('使用者收合主視窗，懸浮窗已顯示')

    def restore_main(self):
        self.floating_mode=False
        self.showNormal()
        self.overlay.hide()
        self.raise_()
        self.activateWindow()
        logging.info('主視窗已重新顯示')

    def capture_status(self):
        if not self.auto_active:
            return '視窗內容擷取｜等待牌桌；其他視窗遮擋不影響讀取，請勿最小化牌桌。'
        fresh=self.capture_last_frame>0 and monotonic()-self.capture_last_frame<2
        return f'視窗內容擷取｜{"正常更新" if fresh else "等待新畫面"}\n{self.capture_title}\n其他視窗可遮擋牌桌；牌桌最小化或停止更新時暫停建議。'

    def save_control_settings(self,options):
        from control_settings import write
        write(options,self.control_path)
        self.apply_control_options(options)

    def poll_control_settings(self):
        from control_settings import read
        try:
            options=read(self.control_path)
            if options!=self.control_options: self.apply_control_options(options)
        except (ValueError,OSError):
            self.statusBar().showMessage('設定檔無效，繼續使用最後有效設定')

    def apply_control_options(self,options):
        from control_settings import validate
        previous=self.control_options
        self.control_options=validate(options)
        self.analysis.apply_display_options(self.control_options)
        self.live_numbers.hide()
        if previous['auto_dock']!=self.control_options['auto_dock']:
            self.dock_key=None
            if self.auto_active and self.vision_worker:
                table=next((item for item in list_tables() if item.handle==self.vision_worker.handle),None)
                if table:self.dock_beside_table(table)
        if self.vision_worker: self.vision_worker.refresh_ms=self.control_options['refresh_ms']
        index=self.settings.iterations.findData(self.control_options['iterations'])
        self.settings.iterations.blockSignals(True)
        self.settings.iterations.setCurrentIndex(index)
        self.settings.iterations.blockSignals(False)
        changed=any(previous[key]!=self.control_options[key] for key in ('iterations','opponent_range','bet_percentages'))
        if changed and self.detector.state is not None and not self.uncertain:
            self.equity_cache=None
            if self.auto_active:
                generation=self.generation
                self.accept_auto_table(self.auto_generation,self.detector.state.to_dict())
                if self.generation==generation and not self.uncertain:
                    self.start_analysis()
            else:
                self.start_analysis()

    @staticmethod
    def add_button(layout, text, callback):
        button = QPushButton(text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def show_error(self, message):
        self.live_cards.show()
        self.uncertain = True
        self.result = None
        self.generation += 1
        for worker in self.workers:
            from .equity_preview import EquityPreviewWorker
            if not isinstance(worker,EquityPreviewWorker): worker.cancel.set()
        self.statusBar().showMessage(f'資料不確定：{message}')
        self.analysis.invalidate(f'資料不確定，請確認：{message}')
        self.overlay.invalidate(f'資料不確定：{message}')
        self.mode_label.setText(f'請修正：{message}')
        if self.auto_active:
            self.analysis.invalidate(f'{message}\n\n確認可靠資料後會自動更新，無需按按鈕。')
            if self.card_threat_result and not any(word in message for word in ('牌面','底牌','擷取','視窗','休息')):
                self.analysis.render_card_threats(self.card_threat_result,'金額或人數確認中；行動暫停')
            self.mode_label.setText('自動追蹤中，等待可靠的牌桌資料。')
            if not any(word in message for word in ('牌面','底牌','擷取','視窗','休息','牌背','持牌')):
                self.render_equity_preview()

    def refresh_table_choices(self):
        previous=self.table_choice.currentData()
        try:
            tables=[table for table in list_tables() if '盲注' in table.title or 'blind' in table.title.lower()]
            self.table_choice.blockSignals(True)
            self.table_choice.clear()
            self.table_choice.addItem('自動選擇可用牌桌',None)
            for table in tables: self.table_choice.addItem(table.title,table.handle)
            index=self.table_choice.findData(previous)
            self.table_choice.setCurrentIndex(max(0,index))
        finally:
            self.table_choice.blockSignals(False)

    def selected_table(self,tables):
        handle=self.table_choice.currentData()
        if handle is None: return tables[0]
        selected=next((table for table in tables if table.handle==handle),None)
        if selected is None: raise ValueError('所選牌桌已關閉，請重新選擇牌桌')
        return selected

    def change_table(self,*_):
        if self.auto_active or self.auto_waiting:
            if self.stop_auto(): self.toggle_auto()

    def accept_equity_view(self,token,observation):
        if token!=self.auto_generation or not self.auto_active: return
        from .equity_preview import EquityPreviewWorker
        if observation is None:
            self.partial_equity_key=None
            self.partial_equity_result=None
            for worker in self.workers:
                if isinstance(worker,EquityPreviewWorker): worker.cancel.set()
            return
        key=(token,tuple(observation['hero']),tuple(observation['board']),
            tuple(observation['active_seats']),self.control_options['opponent_range'])
        self.partial_equity_time=monotonic()
        if key==self.partial_equity_key:
            self.render_equity_preview()
            return
        self.partial_equity_key=key
        self.partial_equity_result=None
        for worker in self.workers:
            if isinstance(worker,EquityPreviewWorker): worker.cancel.set()
        worker=EquityPreviewWorker(key,observation,self.control_options['opponent_range'],self)
        worker.succeeded.connect(self.accept_equity_result)
        worker.finished.connect(lambda:self.worker_finished(worker))
        self.workers.append(worker)
        worker.start()

    def accept_equity_result(self,key,result):
        if key!=self.partial_equity_key or not self.auto_active: return
        self.partial_equity_result=result
        self.render_equity_preview()

    def render_equity_preview(self):
        if self.partial_equity_result is None or self.result is not None or self.replay_mode: return
        if monotonic()-self.partial_equity_time>1.5: return
        self.analysis.render(self.partial_equity_result)
        self.overlay.render({**self.partial_equity_result,'action_text':'勝率已估算｜下注暫停，金額待確認',
            'sizing_advice':'下注金額：等待確認'}, {})

    def form_edited(self):
        self.simple_dirty = True
        self.replay_mode = False
        self.result = None
        self.generation += 1
        for worker in self.workers:
            worker.cancel.set()
        if self.auto_watch or self.auto_active or self.auto_waiting:
            self.mode_label.setText('正在自動追蹤，資料確認後會立即更新。')
            self.analysis.invalidate('正在確認牌桌資料，確認後會自動顯示分析。')
            self.overlay.invalidate('正在確認資料，分析會自動更新')
            return
        self.mode_label.setText('輸入已變更，按「分析」查看結果。')
        if self.auto_active and self.auto_category:
            self.analysis.invalidate(f'目前牌型：{self.auto_category}\n\n金額已變更，按「分析」計算勝率與期望值。')
        else:
            self.analysis.invalidate('選好牌、填好金額後，按「分析」。')
        self.overlay.invalidate('輸入已變更，等待分析')

    def set_live_layout(self):
        self.analysis.heading.hide()
        self.analysis.footer.hide()
        self.advanced_toggle.setChecked(False)
        self.advanced_toggle.hide()
        self.advanced_scroll.hide()
        self.guide.hide()
        self.mode_label.hide()
        self.auto_status.hide()
        self.mode_label.setText('牌桌資料會自動讀取，分析結果會自動更新。')
        self.statusBar().showMessage('即時分析已開啟，等待牌桌資料。')
        self.set_card_controls_enabled(False)
        self.simple_form.setVisible(False)
        self.analyze_button.setVisible(False)
        self.clear_button.setVisible(False)
        self.demo_button.setVisible(False)
        self.resize(780,960)

    def toggle_auto(self):
        if self.auto_active or self.auto_waiting:
            self.stop_auto()
            return
        self.auto_watch = True
        self.auto_monitor.start()
        self.set_live_layout()
        try:
            tables = [table for table in list_tables() if '盲注' in table.title or 'blind' in table.title.lower()]
            if not tables:
                self.auto_waiting = True
                self.auto_button.setText('停止等待牌桌')
                self.auto_status.setText('等待開啟牌局視窗，找到牌桌後會自動開始')
                self.analysis.invalidate('等待牌桌；開啟牌局後會自動追蹤。')
                return
            selected = self.selected_table(tables)
            self.capture_title=selected.title
            self.capture_last_frame=0.0
            self.clear_simple()
            self.save_control_settings({**self.control_options,'bounty_active':False,
                'bounty_known':False,'rake_known':False})
            self.set_live_layout()
            self.auto_active = True
            self.auto_generation += 1
            token = self.auto_generation
            self.auto_category = None
            self.equity_cache = None
            self.auto_button.setText('停止自動辨識')
            self.auto_status.setText('正在讀取牌桌視窗內容；可被其他視窗遮擋，請勿最小化')
            self.dock_key=None
            QTimer.singleShot(0,lambda:self.dock_beside_table(selected))
            self.vision_worker = VisionWorker(selected.handle, self, diagnostic_path=self.data_dir/'辨識狀態.json')
            self.vision_worker.refresh_ms=self.control_options['refresh_ms']
            self.vision_worker.cards.connect(lambda result: self.accept_auto_cards(token, result))
            self.vision_worker.hero_view.connect(lambda result: self.accept_auto_hero(token,result))
            self.vision_worker.table.connect(lambda result: self.accept_auto_table(token, result))
            self.vision_worker.amounts.connect(lambda result: self.accept_auto_amounts(token, result))
            self.vision_worker.view.connect(lambda result: self.accept_auto_view(token, result))
            self.vision_worker.equity_view.connect(lambda result:self.accept_equity_view(token,result))
            self.vision_worker.unavailable.connect(lambda message: self.accept_auto_unavailable(token, message))
            self.vision_worker.status.connect(lambda message: self.accept_auto_status(token, message))
            self.vision_worker.timing.connect(lambda milliseconds: self.accept_auto_timing(token, milliseconds))
            self.vision_worker.start()
        except Exception as error:
            self.auto_status.setText(str(error))

    def dock_beside_table(self,table):
        if self.floating_mode or not self.auto_active or not self.control_options['auto_dock']: return
        from .window_placement import table_screen,free_regions,choose_region
        screen,rect=table_screen(table,QApplication.screens())
        area=screen.availableGeometry()
        key=(table.handle,rect,(area.x(),area.y(),area.width(),area.height()))
        if self.dock_key is not None and key[0]==self.dock_key[0] and key[2]==self.dock_key[2]:
            if max(abs(a-b) for a,b in zip(rect,self.dock_key[1]))<80:return
        self.dock_key=key
        regions=free_regions(key[2],rect)
        target=choose_region(regions,self.minimumWidth()+12,self.minimumHeight()+50)
        if target is None:
            self.statusBar().showMessage('牌桌旁空間不足，保留主視窗；可手動調整牌桌大小。')
            return
        x,y,width,height=target
        self.overlay.hide()
        self.showNormal()
        # 保留標題列與視窗邊框空間。
        self.resize(min(800,width-12),height-50)
        self.move(x,y)
        self.statusBar().showMessage('已自動移到牌桌旁；可在調整設定關閉。')

    def monitor_auto(self):
        if not self.auto_watch:
            return
        tables = [table for table in list_tables() if '盲注' in table.title or 'blind' in table.title.lower()]
        if self.auto_waiting and tables:
            self.auto_waiting = False
            self.toggle_auto()
        elif self.auto_active and self.vision_worker and self.vision_worker.handle not in {table.handle for table in tables}:
            if self.stop_auto():
                self.toggle_auto()

        elif self.auto_active and self.vision_worker:
            selected=next((table for table in tables if table.handle==self.vision_worker.handle),None)
            if selected: self.dock_beside_table(selected)

    def set_card_controls_enabled(self, enabled):
        for button in self.simple_form.hero + self.simple_form.board:
            button.setEnabled(enabled)

    def accept_auto_status(self, token, message):
        if token != self.auto_generation or not self.auto_active:
            return
        if message:
            self.auto_category = None
            self.show_error(message)
            normal_wait = message.startswith(('自身沒有可見底牌','牌局休息中','正在確認牌面'))
            self.auto_status.setText(f'{"等待牌局" if normal_wait else "暫停分析"}：{message}')
            if normal_wait:
                self.statusBar().showMessage(message)
                self.mode_label.setText('正在追蹤牌桌；有可靠底牌後自動分析。')

    def accept_auto_unavailable(self, token, message):
        if token == self.auto_generation and self.auto_active:
            self.accept_equity_view(token,None)
            self.show_error(message)
            self.capture_last_frame=0.0
            self.last_hero_names=''
            self.card_threat_result=None
            self.card_threat_key=None
            self.analysis.invalidate('畫面暫停，等待恢復')
            self.live_cards.setText('底牌：擷取暫停，等待畫面恢復')
            self.live_numbers.setText(f'牌桌資料暫停更新\n{message}')

    def accept_auto_timing(self, token, milliseconds):
        if token==self.auto_generation and self.auto_active: self.capture_last_frame=monotonic()
        if token == self.auto_generation and self.auto_active and not self.uncertain:
            self.auto_status.setText(f'自動辨識中｜每幀 {milliseconds:.0f} 毫秒｜連續三幀確認牌面')

    def accept_auto_amounts(self, token, amounts):
        if token != self.auto_generation or not self.auto_active:
            return
        from .equity_preview import EquityPreviewWorker
        state=self.detector.state
        if state is not None and self.result is not None:
            changed=any(value is None or abs(value-old)>.01 for value,old in
                ((amounts.pot,state.pot),(amounts.call_amount,state.call_amount),(amounts.hero_stack,state.hero_stack)))
            changed=changed or any(p.current_bet!=amounts.seat_bets.get(p.seat) for p in state.players)
            if changed:
                self.result=None
                self.generation+=1
                for worker in self.workers:
                    if not isinstance(worker,EquityPreviewWorker): worker.cancel.set()
                self.analysis.invalidate('下注金額已改變，正在確認新的跟注額；舊建議已撤回')
                self.overlay.invalidate('下注金額已變動，舊建議已撤回')
        bb=getattr(amounts,'bb_display',False)
        self.amount_unit_notice.setText('牌桌目前顯示大盲單位，請切換成籌碼顯示。換算可能有四捨五入誤差。' if bb else '')
        self.amount_unit_notice.setVisible(bb)
        def number(value):
            return f'{value:,.0f}' if value is not None else '辨識中'
        if amounts.paused:
            self.live_numbers.setText(f'牌局休息中\n自身籌碼 {number(amounts.hero_stack)}\n恢復發牌後會自動更新')
            return
        stacks='　'.join(f'{seat}位 {value:,.0f}' for seat,value in amounts.seat_stacks.items()
            if seat!=0 and amounts.field_reliable.get(f'stack_{seat}',False))
        self.live_numbers.setText(f'底池 {number(amounts.pot)}　跟注 {number(amounts.call_amount)}　自己 {number(amounts.hero_stack)}\n對手籌碼：{stacks or "確認中"}')

    def accept_auto_view(self, token, observation):
        if token != self.auto_generation or not self.auto_active:
            return
        amounts, players = observation['amounts'], observation['players']
        if amounts.reliable:
            hero = observation['hero_active']
            count = f'對手持牌 {len(players.active_seats)} 人；自身牌面待確認' if hero is None else f'仍持牌 {len(players.active_seats)+int(hero)} 人'
            bets = '　'.join(f'座位{s}：{amount:,.0f}' for s, amount in amounts.seat_bets.items() if amount)
            stacks='　'.join(f'{s}位 {amounts.seat_stacks[s]:,.0f}' for s in players.active_seats
                if s in amounts.seat_stacks and amounts.field_reliable.get(f'stack_{s}',False))
            self.live_numbers.setText(f'底池 {amounts.pot:,.0f}　跟注 {amounts.call_amount:,.0f}　自己 {amounts.hero_stack:,.0f}\n對手籌碼：{stacks or "確認中"}｜{count}')

    def accept_auto_cards(self, token, detection):
        if token != self.auto_generation or not self.auto_active:
            return
        suits={'s':'黑桃','c':'梅花','h':'紅心','d':'方塊'}
        ranks={'T':'十','J':'傑克','Q':'皇后','K':'國王','A':'王牌'}
        def names(cards):
            return '、'.join(suits[c[1]]+ranks.get(c[0],c[0]) for c in cards)
        self.live_cards.setText(f'底牌已確認：{names(detection.hero)}\n公共牌：{names(detection.board) or "尚未翻牌"}' if detection.hero else '底牌：目前畫面沒有可見底牌')
        self.uncertain = False
        self.simple_form.blockSignals(True)
        try:
            for buttons, values in [(self.simple_form.hero, detection.hero), (self.simple_form.board, detection.board)]:
                for index, button in enumerate(buttons):
                    button.set_card(values[index] if index < len(values) else None)
        finally:
            self.simple_form.blockSignals(False)
        self.form_edited()
        self.auto_status.setText(f'牌面已確認｜匹配信心 {detection.confidence:.0%}｜每幀 {detection.milliseconds:.0f} 毫秒')
        if len(detection.hero) == 2:
            self.auto_category = evaluate_hand(detection.hero, detection.board).category
            self.analysis.invalidate(f'目前牌型：{self.auto_category}\n\n正在確認金額與持牌人數，確認後自動計算。')
            self.mode_label.setText('自動追蹤中，無需操作分析按鈕。')
            if len(detection.board) in (3,4,5):
                key=(tuple(detection.hero),tuple(detection.board))
                if key!=self.card_threat_key:
                    from itertools import combinations
                    from poker.cards import DECK
                    from poker.threats import calculate_threats
                    blocked=set(detection.hero+detection.board)
                    hands=[list(pair) for pair in combinations(DECK,2) if not blocked.intersection(pair)]
                    temporary=PokerTableState(hero_cards=list(detection.hero),board=list(detection.board),hero_seat=0,
                        players=[{'seat':0},{'seat':1}],ranges={'1':hands})
                    threats=calculate_threats(temporary)
                    self.card_threat_key=key
                    self.card_threat_result={'street':temporary.street,'hand_strength':self.auto_category,
                        'hero_cards':list(detection.hero),'community_cards':list(detection.board),
                        'beating_hand_types':threats.beating_hand_types,'threats_details':threats.to_dict()}
                self.analysis.render_card_threats(self.card_threat_result,'金額確認中；行動暫停')
        else:
            self.auto_category = None
            self.analysis.invalidate('等待底牌：尚未發牌或已棄牌。')
            self.mode_label.setText('牌面追蹤中，等待下一手底牌。')

    def accept_auto_hero(self,token,observation):
        if token!=self.auto_generation or not self.auto_active: return
        hero,board=observation['hero'],observation['board']
        if not hero or board is None or not board:
            self.card_threat_result=None
            self.card_threat_key=None
            self.analysis.clear_threat_pictures()
        if hero is None:
            if self.last_hero_names and monotonic()-self.last_hero_time<=.8:
                self.live_cards.setText(f'最近讀到：{self.last_hero_names}｜目前被遮擋，暫停決策')
            else:
                self.last_hero_names=''
                self.live_cards.setText('底牌：正在確認，暫不沿用上一手')
            if not self.uncertain:
                self.show_error('底牌目前未確認，暫停決策')
            else:
                self.analysis.invalidate('底牌目前未確認，暫停決策')
            return
        if not hero:
            self.last_hero_names=''
            self.live_cards.setText('底牌：目前畫面沒有可見底牌')
            return
        suits={'s':'黑桃','c':'梅花','h':'紅心','d':'方塊'}
        ranks={'T':'十','J':'傑克','Q':'皇后','K':'國王','A':'王牌'}
        def names(cards): return '、'.join(suits[c[1]]+ranks.get(c[0],c[0]) for c in cards)
        self.analysis.card_strip.show()
        self.last_hero_names=names(hero)
        self.last_hero_time=monotonic()
        public='正在確認；底牌已獨立讀取' if board is None else names(board) or '尚未翻牌'
        self.live_cards.setText(f'底牌已確認：{names(hero)}\n公共牌：{public}')

    def stop_auto(self):
        self.amount_unit_notice.hide()
        self.partial_equity_key=None
        self.partial_equity_result=None
        if self.vision_worker:
            self.vision_worker.requestInterruption()
            if not self.vision_worker.wait(3000):
                self.auto_status.setText('正在停止辨識，請稍候')
                return False
            self.vision_worker.deleteLater()
            self.vision_worker = None
        self.auto_active = False
        self.last_hero_names=''
        self.auto_waiting = False
        self.auto_watch = False
        self.auto_monitor.stop()
        self.auto_generation += 1
        self.auto_button.setText('開始自動辨識')
        self.auto_status.setText('已停止自動辨識，可手動選牌')
        self.overlay.invalidate('自動辨識已停止')
        self.advanced_toggle.show()
        self.guide.show()
        self.mode_label.show()
        self.auto_status.show()
        self.card_threat_key=None
        self.card_threat_result=None
        self.set_card_controls_enabled(True)
        self.simple_form.setVisible(True)
        self.analyze_button.setVisible(True)
        self.clear_button.setVisible(True)
        self.demo_button.setVisible(True)
        return True

    def accept_auto_table(self, token, observation):
        if token != self.auto_generation or not self.auto_active:
            return
        try:
            observation=dict(observation)
            observation['ranges']={str(p['seat']):self.control_options['opponent_range'] for p in observation['players']
                if p['seat']!=observation.get('hero_seat') and p.get('active',True) and not p.get('folded',False)}
            state = PokerTableState.from_dict(observation)
            event = self.detector.update(state)
            if self.detector.last_error:
                raise ValueError(self.detector.last_error)
            self.uncertain = False
            self.simple_dirty = False
            self.replay_mode = False
            self.render_state(state.to_dict())
            active = [p for p in state.players if p.active and not p.folded]
            bets = '　'.join(f'座位{p.seat}：{p.current_bet:,.0f}' for p in state.players if p.current_bet)
            stacks='　'.join(f'{p.seat}位 {p.stack:,.0f}' for p in active if p.seat!=state.hero_seat and p.stack_known)
            self.live_numbers.setText(f'底池 {state.pot:,.0f}　跟注 {state.call_amount:,.0f}　自己 {state.hero_stack:,.0f}\n對手籌碼：{stacks or "確認中"}｜對手 {len(active)-1} 人')
            if event:
                self.repository.save_event(event)
                self.editor.setPlainText(json.dumps(editable_state(state.to_dict()), ensure_ascii=False, indent=2))
                self.sync_form(state.to_dict())
                self.start_analysis()
            elif self.result is None and not self.workers:
                self.start_analysis()
        except Exception as error:
            self.show_error(str(error))

    def analyze_simple(self):
        try:
            data = self.simple_form.to_data()
            data['fold_probability'] = self.settings.fold.value()
            self.editor.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
            self.apply_editor()
        except Exception as error:
            self.show_error(str(error))

    def clear_simple(self):
        self.simple_form.blockSignals(True)
        try:
            self.simple_form.clear()
        finally:
            self.simple_form.blockSignals(False)
        self.form_edited()
        self.uncertain = False
        self.editor.setPlainText(json.dumps(editable_state(PokerTableState().to_dict()), ensure_ascii=False, indent=2))
        self.current.setText('尚未建立牌局')
        self.mode_label.setText('先選兩張底牌，再填金額，最後按「分析」。')
        self.statusBar().showMessage('已清空輸入，歷史紀錄仍保留')

    def sync_form(self, data):
        self.simple_form.blockSignals(True)
        self.settings.fold.blockSignals(True)
        try:
            self.simple_form.load_data(data)
            self.settings.fold.setValue(data.get('fold_probability', 0))
        finally:
            self.simple_form.blockSignals(False)
            self.settings.fold.blockSignals(False)
        self.simple_dirty = False

    def apply_editor(self):
        try:
            data = json.loads(self.editor.toPlainText())
            data['source'] = '手動'
            state = PokerTableState.from_dict(data)
            event = self.detector.update(state)
            if event is None:
                error = self.detector.last_error
                if error:
                    self.show_error(error)
                else:
                    if self.simple_dirty:
                        self.simple_dirty = False
                        self.uncertain = False
                        self.start_analysis()
                        return
                    if self.uncertain:
                        self.uncertain = False
                        self.start_analysis()
                        return
                    self.statusBar().showMessage('資料無變化，不重新計算')
                return
            self.replay_mode = False
            self.uncertain = False
            self.repository.save_event(event)
            self.editor.setPlainText(json.dumps(editable_state(self.detector.state.to_dict()), ensure_ascii=False, indent=2))
            self.sync_form(self.detector.state.to_dict())
            self.render_state(self.detector.state.to_dict())
            self.refresh_history()
            self.start_analysis()
        except Exception as error:
            self.show_error(str(error))

    def render_state(self, data):
        self.current.setText(f"自身底牌：{' '.join(data.get('hero_cards', []))}\n公共牌：{' '.join(data.get('community_cards', []))}\n街次：{data.get('street', '')}　玩家：{len(data.get('players', []))}\n底池：{data.get('pot', 0):,.2f}　跟注額：{data.get('call_amount', 0):,.2f}")

    def start_analysis(self):
        for worker in self.workers:
            worker.cancel.set()
        self.result = None
        self.generation += 1
        generation = self.generation
        self.analysis.invalidate('狀態已更新，背景計算中…')
        self.mode_label.setText('正在計算，仍可修改輸入；再次按分析會更新。')
        self.overlay.invalidate('背景計算中…')
        cached = self.equity_cache if self.auto_active and self.equity_cache and self.equity_cache[0] == AnalysisEngine.equity_key(self.detector.state, self.settings.seed.value()) else None
        iterations = 2000 if self.auto_active else self.settings.iterations.currentData()
        worker = AnalysisWorker(self.detector.version, self.detector.state, iterations, self.settings.seed.value(), self, cached_equity=cached)
        if self.auto_active:
            self.mode_label.setText('自動更新中；牌面或對手改變時重新估算勝率。')
        worker.succeeded.connect(lambda version, result: self.accept_analysis(generation, version, result))
        worker.failed.connect(lambda version, message: self.accept_failure(generation, version, message))
        worker.finished.connect(lambda: self.worker_finished(worker))
        self.workers.append(worker)
        self.statusBar().showMessage(f'牌局版本 {self.detector.version}：計算中')
        worker.start()

    def accept_analysis(self, generation, version, result):
        if generation == self.generation and not self.uncertain:
            self.analysis_ready(version, result)

    def accept_failure(self, generation, version, message):
        if generation == self.generation:
            self.analysis_failed(version, message)

    def worker_finished(self, worker):
        if worker in self.workers:
            self.workers.remove(worker)
        worker.deleteLater()

    def analysis_ready(self, version, result):
        if getattr(self,'_closed',False) or version != self.detector.version:
            return
        self.result = result.to_dict()
        self.result['pot']=self.detector.state.pot
        self.result['hero_cards']=list(self.detector.state.hero_cards)
        self.result['community_cards']=list(self.detector.state.community_cards)
        self.result['target_simulations']=self.control_options['iterations']
        if self.detector.state is not None:
            from dataclasses import asdict
            from poker.bet_simulator import simulate_bets
            state=self.detector.state
            self.result['bet_scenarios']=[asdict(row) for row in simulate_bets(state.pot,state.effective_stack,result.equity,state.fold_probability,self.control_options['bet_percentages'])]
        if self.auto_active:
            self.equity_cache = (AnalysisEngine.equity_key(self.detector.state, self.settings.seed.value()), EquityResult(**result.equity_details))
            self.result['facing_all_in']=any(p.all_in for p in state.players if p.seat!=state.hero_seat and p.active and not p.folded)
            self.result.update(live=True, range_assumed=True, street=self.detector.state.street, call_amount=self.detector.state.call_amount,
                effective_stack=self.detector.state.effective_stack,
                opponents=sum(p.active and not p.folded and p.seat != self.detector.state.hero_seat for p in self.detector.state.players))
            if any(not p.stack_known for p in self.detector.state.players if p.active and not p.folded):
                self.result.update(spr=None, bet_scenarios=[], stack_unknown=True)
        self.repository.save_analysis(version, self.result)
        if not self.replay_mode:
            self.analysis.render(self.result)
            self.live_cards.show()
            self.result['action_text']=self.analysis.action_label.text()
            self.result['sizing_advice']=self.analysis.sizing_label.text()
            self.overlay.render(self.result, self.detector.state.to_dict())
            self.statusBar().showMessage(f'版本 {version}：分析已更新')
            self.mode_label.setText('分析完成。換牌或改金額後，再按「分析」。')
            if self.auto_active:
                self.mode_label.setText('即時分析中：畫面變動會自動更新，無需按鈕。')
        self.refresh_history()
        if self.auto_active and result.simulation_count < self.control_options['iterations']:
            self.start_refinement(result.simulation_count)

    def start_refinement(self, current_samples):
        """保留快速估算，背景增加樣本；新的牌局版本會取消舊工作。"""
        generation = self.generation
        target=self.control_options['iterations']
        worker = AnalysisWorker(self.detector.version, self.detector.state, min(10000 if current_samples<10000 else target,target),
            self.settings.seed.value(), self)
        worker.succeeded.connect(lambda version, result: self.accept_analysis(generation, version, result))
        worker.failed.connect(lambda version, message: self.accept_failure(generation, version, message))
        worker.finished.connect(lambda: self.worker_finished(worker))
        self.workers.append(worker)
        worker.start()
        self.mode_label.setText('快速估算已顯示；背景提高精度，牌桌資料持續更新。')

    def analysis_failed(self, version, message):
        if version == self.detector.version:
            self.show_error(message)

    def recalculate(self, *_):
        if self.detector.state is not None and not self.uncertain and not self.simple_dirty:
            self.start_analysis()

    def update_fold(self, value):
        try:
            data = self.control_data()
            data['fold_probability'] = value
            self.editor.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
            self.apply_editor()
        except Exception as error:
            self.show_error(str(error))

    def load_demo(self):
        if self.auto_active and not self.stop_auto():
            return
        self.sync_form(demo_data())
        self.editor.setPlainText(json.dumps(demo_data(), ensure_ascii=False, indent=2))
        self.apply_editor()

    def demo_change(self):
        try:
            data = json.loads(self.editor.toPlainText())
            data['pot'] += 400
            data['call_amount'] += 400
            for player in data['players']:
                if player['seat'] != data.get('hero_seat', 1):
                    player['current_bet'] += 400
                    player['total_invested'] += 400
                    player['stack'] = max(0, player['stack']-400)
                    player['action'] = '加注'
                    break
            self.editor.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
            self.apply_editor()
        except Exception as error:
            self.show_error(str(error))

    def apply_range(self):
        try:
            data = self.control_data()
            value = ['tight', 'standard', 'loose', self.range_text.toPlainText()][self.range_choice.currentIndex()]
            data['ranges'] = {str(p['seat']): value for p in data['players'] if p['seat'] != data.get('hero_seat', 1) and not p.get('folded', False)}
            self.editor.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
            self.apply_editor()
        except Exception as error:
            self.show_error(str(error))

    def control_data(self):
        if self.simple_dirty:
            return self.simple_form.to_data()
        return json.loads(self.editor.toPlainText())

    def save_range(self):
        path, _ = QFileDialog.getSaveFileName(self, '儲存範圍', str(self.data_dir / '對手範圍.json'), '範圍檔案 (*.json)')
        if path:
            try:
                Path(path).write_text(json.dumps({'choice': self.range_choice.currentIndex(), 'text': self.range_text.toPlainText()}, ensure_ascii=False), encoding='utf-8')
            except Exception as error:
                self.show_error(str(error))

    def load_range(self):
        path, _ = QFileDialog.getOpenFileName(self, '載入範圍', str(self.data_dir), '範圍檔案 (*.json)')
        if path:
            try:
                data = json.loads(Path(path).read_text(encoding='utf-8'))
                self.range_choice.setCurrentIndex(int(data['choice']))
                self.range_text.setPlainText(data['text'])
                self.apply_range()
            except Exception as error:
                self.show_error(str(error))

    def start_capture(self):
        if not self.stop_capture():
            return
        source = ScreenCapture(self.source_index.value()) if self.source.currentIndex() == 0 else ObsCapture(self.source_index.value())
        self.capture_worker = CaptureWorker(source, self)
        self.capture_worker.error.connect(lambda message: self.statusBar().showMessage(f'擷取錯誤：{message}'))
        self.capture_worker.start()

    def stop_capture(self):
        if self.capture_worker:
            self.capture_worker.requestInterruption()
            if not self.capture_worker.wait(3000):
                self.statusBar().showMessage('擷取仍在停止中，請稍候')
                return False
            self.capture_worker.deleteLater()
            self.capture_worker = None
        return True

    def poll_frame(self):
        if self.capture_worker:
            frame = self.capture_worker.buffer.get()
            if frame is not None:
                self.view.set_frame(frame)

    def save_profile(self):
        path, _ = QFileDialog.getSaveFileName(self, '儲存區域', str(self.profile_dir / 'poker_table_profile.json'), '區域檔案 (*.json)')
        if path:
            try:
                self.view.profile.save(path)
                self.statusBar().showMessage('區域已儲存')
            except Exception as error:
                self.show_error(str(error))

    def load_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, '載入區域', str(self.profile_dir), '區域檔案 (*.json)')
        if path:
            try:
                self.view.profile = TableProfile.load(path)
                self.view.update()
            except Exception as error:
                self.show_error(str(error))

    def refresh_history(self):
        self.history.clear()
        for item in self.repository.list_events():
            from datetime import datetime
            timestamp = item.get('timestamp', 0)
            time_text = datetime.fromtimestamp(timestamp).astimezone().strftime('%Y-%m-%d %H:%M:%S') if timestamp else '未記錄時間'
            self.history.addItem(f"版本 {item['version']}　{time_text}")
            self.history.item(self.history.count()-1).setData(Qt.ItemDataRole.UserRole, item)

    def replay(self, item):
        event = item.data(Qt.ItemDataRole.UserRole)
        self.replay_mode = True
        data = event.get('current_state', event.get('state', {}))
        self.sync_form(data)
        self.render_state(data)
        self.mode_label.setText(f"歷史回放：版本 {event['version']}。可返回目前牌局。")
        analysis = self.repository.get_analysis(event['version'])
        if analysis:
            self.analysis.render(analysis)
            self.overlay.render(analysis, data)
        else:
            self.analysis.invalidate('當時分析未完成或已取消，無可回放結果')
            self.overlay.invalidate('歷史版本無分析結果')
        self.statusBar().showMessage(f"回放版本 {event['version']}")

    def return_live(self):
        self.replay_mode = False
        if self.uncertain:
            self.analysis.invalidate('資料不確定，請修正後重新套用')
            self.overlay.invalidate('資料不確定，請修正後重新套用')
            return
        if self.simple_dirty:
            self.analysis.invalidate('輸入已變更，請按「分析」。')
            self.overlay.invalidate('輸入已變更，等待分析')
            return
        if self.detector.state:
            self.sync_form(self.detector.state.to_dict())
            self.render_state(self.detector.state.to_dict())
            self.mode_label.setText('目前牌局：換牌或改金額後，再按「分析」。')
            if self.result:
                self.analysis.render(self.result)
                self.overlay.render(self.result, self.detector.state.to_dict())
            else:
                self.analysis.invalidate('目前版本分析尚未完成')

    def install_update(self, release, package):
        import os
        import subprocess
        from app_paths import install_root
        from version import PRODUCT_PATH
        root=install_root()
        if root is None:
            QMessageBox.information(self,'更新','請先安裝正式版本，再使用自動更新。')
            return
        updater=root/'Updater.exe'
        if not updater.is_file():
            QMessageBox.warning(self,'更新失敗','找不到更新工具，請重新執行安裝程式修復。')
            return
        try:
            subprocess.Popen([str(updater),'--product',str(PRODUCT_PATH),'--root',str(root),
                              '--data',str(self.data_dir),'--package',str(package),'--wait-pid',str(os.getpid())],
                             creationflags=subprocess.CREATE_NO_WINDOW, cwd=str(root))
        except OSError as error:
            QMessageBox.warning(self,'更新失敗',f'無法啟動更新工具：{error}')
            return
        self._close_pending=True
        self.close()

    def resume_pending_close(self):
        if getattr(self,'_close_pending',False):
            QTimer.singleShot(0,self.close)

    def closeEvent(self, event):
        controller=getattr(self,'update_controller',None)
        if controller is not None and not controller.shutdown():
            self._close_pending=True
            event.ignore()
            return
        if not self.stop_auto():
            event.ignore()
            return
        if not self.stop_capture():
            event.ignore()
            return
        for worker in self.workers:
            worker.cancel.set()
        for worker in list(self.workers):
            if not worker.wait(5000):
                event.ignore()
                return
        self.overlay.close()
        self.control_timer.stop()
        self.frame_timer.stop()
        self._closed=True
        self.generation+=1
        self.repository.close()
        event.accept()
        logging.info('背景工作與資料庫已關閉，要求程式退出')
        QTimer.singleShot(0,QApplication.instance().quit)
