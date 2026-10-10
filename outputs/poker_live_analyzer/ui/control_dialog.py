"""可立即套用及取消的設定視窗。"""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QWidget,QTabWidget,QSpinBox,
    QComboBox,QCheckBox,QPushButton,QDialogButtonBox,QLabel,QColorDialog,QHBoxLayout)
from control_settings import DEFAULTS,LIMITS,validate

class ControlDialog(QDialog):
    def __init__(self,values,apply_callback,status_callback,parent=None,update_controller=None,calibration_callback=None):
        super().__init__(parent)
        from .fonts import interface_font
        self.setFont(interface_font())
        self.setWindowTitle('調整設定')
        self.resize(520,620)
        self.apply_callback=apply_callback
        self.fields={}
        self.colors={}
        layout=QVBoxLayout(self)
        tabs=QTabWidget()
        layout.addWidget(tabs)
        for title,entries in [('介面顯示',[('probability_font','勝率與平手字體'),('action_font','行動文字大小'),('text_font','說明文字大小'),('picture_scale','牌型圖片大小（百分比）')]),
            ('分析參數',[('refresh_ms','更新間隔（毫秒）')])]:
            page=QWidget()
            form=QFormLayout(page)
            tabs.addTab(page,title)
            for key,label in entries:
                spin=QSpinBox()
                spin.setRange(*LIMITS[key])
                self.fields[key]=spin
                form.addRow(label,spin)
            if title=='介面顯示':
                for key,label in [('auto_dock','牌桌開啟後自動縮放到旁邊'),('show_threats','顯示威脅牌型小圖')]:
                    check=QCheckBox(label)
                    self.fields[key]=check
                    form.addRow(check)
                for key,label in [('win_color','勝率'),('tie_color','平手'),('call_color','跟注'),('fold_color','棄牌'),('check_color','過牌'),('wait_color','等待確認'),('matrix_background','翻後矩陣底色'),('matrix_winner','翻後能贏我的牌')]:
                    button=QPushButton('選擇顏色')
                    button.clicked.connect(lambda checked=False,k=key:self.choose_color(k))
                    self.colors[key]=button
                    form.addRow(label,button)
            else:
                for key,label,items in [('iterations','模擬精度',[('快速：一萬次',10000),('標準：五萬次',50000),('精細：十萬次',100000)]),
                    ('opponent_range','對手手牌範圍',[('緊','tight'),('標準','standard'),('寬','loose')])]:
                    combo=QComboBox()
                    for text,value in items: combo.addItem(text,value)
                    self.fields[key]=combo
                    form.addRow(label,combo)
                proportions=QWidget()
                row=QHBoxLayout(proportions)
                self.percentages={}
                for value in (25,33,50,66,75,100,125,150):
                    check=QCheckBox(f'{value}%')
                    self.percentages[value]=check
                    row.addWidget(check)
                form.addRow('下注試算比例',proportions)
                note=QLabel('先給快速結果，再提升到選定精度。\n範圍會影響勝率；下注比例是試算，不是完整最佳策略。')
                note.setWordWrap(True)
                form.addRow(note)
        page=QWidget()
        preflop_form=QFormLayout(page)
        for key,label in [('preflop_background','未確認底色'),('preflop_raise','加注'),('preflop_call','跟注'),('preflop_fold','棄牌'),('preflop_check','過牌')]:
            button=QPushButton('選擇顏色')
            button.clicked.connect(lambda checked=False,k=key:self.choose_color(k))
            self.colors[key]=button
            preflop_form.addRow(label,button)
        note=QLabel('翻前圖表依位置與適用條件顯示，文字固定白色。\n灰色表示尚無對應資料；混合策略依頻率分段顯色。\n自己的底牌使用金色框，翻後切回牌型比較。')
        note.setWordWrap(True)
        preflop_form.addRow(note)
        tabs.addTab(page,'翻前圖表配色')
        page=QWidget()
        calibration_layout=QVBoxLayout(page)
        note=QLabel('一、選擇牌桌，更新預覽。\n二、選擇讀不到的欄位，在預覽上拖曳框選。\n三、驗證讀取正確後，鎖定並儲存。\n\n只需框選需要修正的位置；其他欄位沿用自動定位。\n對手牌背請先設為綠色，金額請使用籌碼顯示。')
        note.setWordWrap(True)
        calibration_layout.addWidget(note)
        self.calibration_button=QPushButton('框選與校準辨識位置')
        self.calibration_button.clicked.connect(calibration_callback or self.open_calibration)
        calibration_layout.addWidget(self.calibration_button)
        calibration_layout.addStretch()
        tabs.addTab(page,'辨識位置')
        if update_controller is not None:
            tabs.addTab(update_controller.create_about_page(),'關於與更新')
        self.status=QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.status_timer=QTimer(self)
        self.status_timer.timeout.connect(lambda:self.status.setText(status_callback()))
        self.status_timer.start(1000)
        self.status.setText(status_callback())
        self.message=QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        restore=QPushButton('恢復預設（按套用才生效）')
        restore.clicked.connect(lambda:self.load(validate({})))
        layout.addWidget(restore)
        buttons=QDialogButtonBox(QDialogButtonBox.Apply|QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Apply).setText('套用')
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        buttons.button(QDialogButtonBox.Cancel).setText('關閉／取消未套用變更')
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.load(values)
    def open_calibration(self):
        from app_paths import user_data_dir
        from .calibration_dialog import CalibrationDialog
        self.calibration_dialog=CalibrationDialog(user_data_dir()/'profiles'/'recognition.json',
            lambda:self.message.setText('辨識位置已儲存；分析器會自動套用。'),self)
        self.calibration_dialog.exec()
    def wait_for_calibration_close(self,callback):
        dialog=getattr(self,'calibration_dialog',None)
        if dialog is None or dialog.worker is None:
            return False
        if not getattr(self,'_calibration_close_pending',False):
            self._calibration_close_pending=True
            dialog.finished.connect(lambda:QTimer.singleShot(0,callback))
        dialog.close()
        return True
    def done(self,result):
        if not self.wait_for_calibration_close(lambda:self.done(result)):
            super().done(result)
    def closeEvent(self,event):
        if self.wait_for_calibration_close(self.close):
            event.ignore()
        else:
            super().closeEvent(event)
    def load(self,values):
        for key,field in self.fields.items():
            if isinstance(field,QSpinBox): field.setValue(values[key])
            elif isinstance(field,QCheckBox): field.setChecked(values[key])
            else: field.setCurrentIndex(field.findData(values[key]))
        for key,button in self.colors.items():
            button.setProperty('color',values[key])
            button.setStyleSheet(f'background: {values[key]}; color: white;')
        for value,check in self.percentages.items(): check.setChecked(value in values['bet_percentages'])
    def choose_color(self,key):
        color=QColorDialog.getColor(parent=self,title='選擇文字顏色')
        if color.isValid():
            self.colors[key].setProperty('color',color.name())
            self.colors[key].setStyleSheet(f'background: {color.name()}; color: white;')
    def apply(self):
        try:
            data={key:(field.value() if isinstance(field,QSpinBox) else field.isChecked() if isinstance(field,QCheckBox) else field.currentData()) for key,field in self.fields.items()}
            data.update({key:button.property('color') for key,button in self.colors.items()})
            data['bet_percentages']=[value for value,check in self.percentages.items() if check.isChecked()]
            self.apply_callback(validate(data))
            self.message.setText('設定已儲存並套用。')
        except (ValueError,OSError) as error: self.message.setText(f'未套用：{error}')
