from poker.amount_units import format_amount
from PySide6.QtCore import Qt, QEvent, QRect, QTimer
from datetime import datetime, timezone, timedelta
from html import escape
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QTableWidget, QTableWidgetItem, QCheckBox, QScrollArea,QBoxLayout
from .hand_picture import hand_picture
from .theme import COLORS, card_style
from .reference_style import ReferenceLabel
from poker.pot_odds import call_ev_near_boundary


class SummaryScrollArea(QScrollArea):
    """說明完整換行，由主視窗負責捲動，避免框內文字被截斷。"""
    def __init__(self, label):
        super().__init__()
        self.label=label
        self.auto_height=False
        label.installEventFilter(self)
        self.viewport().installEventFilter(self)

    def eventFilter(self, watched, event):
        if self.auto_height and event.type() in (QEvent.Resize,QEvent.LayoutRequest):
            self.fit_text()
        return super().eventFilter(watched,event)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.auto_height:self.fit_text()

    def fit_text(self):
        margins=self.widget().layout().contentsMargins() if self.widget() else None
        width=max(100,self.viewport().width()-(margins.left()+margins.right() if margins else 18))
        text_height=self.label.heightForWidth(width)
        height=max(54,min(96,text_height+(margins.top()+margins.bottom() if margins else 18)+4))
        self.label.setToolTip(self.label.text())
        if self.minimumHeight()!=height or self.maximumHeight()!=height:self.setFixedHeight(height)


class AnalysisPanel(QWidget):
    def __init__(self,preflop_path=None):
        super().__init__()
        self.display_options={}
        self.dark_theme=False
        self.fixed_layout=False
        self._view_scale=1.0
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        heading = QLabel('分析結果')
        heading.setStyleSheet('font-size: 20px; font-weight: bold; color: #203b50;')
        layout.addWidget(heading)
        self.probabilities=QWidget()
        probabilities_layout=QHBoxLayout(self.probabilities)
        probabilities_layout.setContentsMargins(0,0,0,0)
        probabilities_layout.setSpacing(12)
        self.win_label=ReferenceLabel(kind="win")
        self.tie_label=ReferenceLabel(kind="tie")
        self.win_label.setStyleSheet('font-size: 32px; font-weight: bold; color: #087d55; background: #e5f6ee; padding: 10px;')
        self.tie_label.setStyleSheet('font-size: 32px; font-weight: bold; color: #7045b4; background: #f0eafa; padding: 10px;')
        probabilities_layout.addWidget(self.win_label)
        probabilities_layout.addWidget(self.tie_label)
        layout.addWidget(self.probabilities)
        self.probabilities.hide()
        self.action_label=ReferenceLabel('等待確認',kind='action')
        self.action_label.setAlignment(Qt.AlignCenter)
        self.action_label.setWordWrap(True)
        layout.addWidget(self.action_label)
        self.set_action('等待確認','#9a6500')
        layout.removeWidget(self.action_label)
        layout.insertWidget(1,self.action_label)
        self.mode_notice=QLabel()
        self.mode_notice.setWordWrap(True)
        self.mode_notice.setStyleSheet('font-size:16px;color:#ffc66d;padding:8px;')
        layout.insertWidget(2,self.mode_notice)
        self.mode_notice.hide()
        self.issue_label=QLabel()
        self.issue_label.setWordWrap(True)
        self.issue_label.setStyleSheet('font-size:17px;color:#FFFFFF;background:#1C1712;border:1px solid #9B7133;border-radius:8px;padding:12px;')
        layout.insertWidget(2,self.issue_label)
        self.issue_label.hide()
        self.last_issue_message=''

        self.sizing_label=QLabel('下注建議：等待可靠牌桌資料')
        self.sizing_label.setWordWrap(True)
        self.sizing_label.setStyleSheet('font-size:17px;padding:10px;')
        layout.addWidget(self.sizing_label)
        self.card_strip=QWidget()
        self.card_strip.setObjectName('surfacePanel')
        card_layout=QVBoxLayout(self.card_strip)
        self.card_text=QLabel('底牌：等待確認\n公共牌：等待確認')
        self.card_text.setWordWrap(True)
        card_layout.addWidget(self.card_text)
        self.hero_picture=QLabel()
        self.board_picture=QLabel()
        layout.addWidget(self.card_strip)
        from .threat_matrix import ThreatMatrix
        self.threat_matrix=ThreatMatrix(preflop_path)
        self.summary = QLabel('選好牌、填好金額後，按「分析」。')
        self.summary.setWordWrap(True)
        self.summary.setAlignment(Qt.AlignTop|Qt.AlignLeft)
        self.summary.setStyleSheet('font-size: 23px; padding: 20px; color: #203b50; background: #eff6f3; border-radius: 12px;')
        self.summary_scroll = SummaryScrollArea(self.summary)
        self.summary_scroll.setWidgetResizable(True)
        self.summary_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.summary_body=QWidget()
        summary_layout=QVBoxLayout(self.summary_body)
        self.summary_layout=summary_layout
        summary_layout.addWidget(self.summary)
        self.threat_pictures=QWidget()
        self.threat_pictures.setObjectName('surfacePanel')
        self.threat_layout=QGridLayout(self.threat_pictures)

        summary_layout.addStretch()
        self.summary_scroll.setWidget(self.summary_body)
        self.summary_body.installEventFilter(self.summary_scroll)
        self.summary_scroll.setMinimumHeight(50)
        self.summary_scroll.setMaximumHeight(90)
        layout.addWidget(self.summary_scroll,1)
        layout.addWidget(self.threat_matrix,1)
        self.details_toggle = QCheckBox('查看詳細數據與下注情境')
        layout.addWidget(self.details_toggle)
        self.details = QWidget()
        details_layout = QVBoxLayout(self.details)
        self.extra = QLabel()
        self.extra.setWordWrap(True)
        details_layout.addWidget(self.extra)
        details_layout.addWidget(self.threat_pictures)
        self.scenarios = QTableWidget(0, 6)
        self.scenarios.setHorizontalHeaderLabels(['底池比例', '下注額', '被跟注後底池', '對手所需勝率', '剩餘大盲與底池比', '期望值'])
        self.scenarios.horizontalHeader().setStretchLastSection(True)
        details_layout.addWidget(self.scenarios)
        note = QLabel('情境假設：一位對手跟注，棄牌率由設定提供。\n補牌為提升自身牌型類別的下一張牌，並非保證勝出的補牌。\n數學情境不代表保證獲利或決策正確。')
        note.setWordWrap(True)
        details_layout.addWidget(note)
        self.details.setVisible(False)
        self.details_toggle.toggled.connect(self.details.setVisible)
        layout.addWidget(self.details)
        footer = QLabel('這是依對手可能拿的牌估算，不能保證贏。')
        footer.setWordWrap(True)
        footer.setStyleSheet('color: #647987;')
        layout.addWidget(footer)
        self.footer=footer
        self.heading=heading
        self.previous_label=QLabel('上一筆結果｜非目前結果<br><br>尚無已完成的建議')
        self.previous_label.setTextFormat(Qt.RichText)
        self.previous_label.setWordWrap(True)
        self.previous_label.setStyleSheet('color:#FFFFFF;font-size:14px;padding:10px;background:#15120F;border:1px solid #9B7133;border-radius:12px;')
        self.previous_label.installEventFilter(self)
        layout.insertWidget(layout.indexOf(self.summary_scroll),self.previous_label)
        self._last_advice=None
        self.reminder_timer=QTimer(self)
        self.reminder_timer.setSingleShot(True)
        self.reminder_timer.timeout.connect(self._end_reminder)

    def _end_reminder(self):
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        effect=self.action_label.graphicsEffect()
        if isinstance(effect,QGraphicsDropShadowEffect):effect.setEnabled(False)

    def remember_advice(self):
        """僅保留顯示快照，絕不拿歷史值計算或執行目前決策。"""
        signature=(self.action_label.text(),self.sizing_label.text())
        previous=self._last_advice
        if previous and previous['signature']!=signature:
            self._show_previous(previous)
        if previous is None or previous['signature']!=signature:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            from PySide6.QtGui import QColor
            effect=QGraphicsDropShadowEffect(self.action_label)
            effect.setColor(QColor('#D8AE62'));effect.setOffset(0,0);effect.setBlurRadius(18)
            self.action_label.setGraphicsEffect(effect)
            self.reminder_timer.start(1200)
        role=self.action_label.property('role_color')
        color={'call_color':'#43dfb9','fold_color':'#f27680','check_color':'#8abaff'}.get(role,'#E8CA8A')
        text=(f'<span style="font-size:13px">上一次｜{datetime.now(timezone(timedelta(hours=8))):%H:%M:%S}｜非目前結果</span><br>'
              f'<span style="color:{color};font-size:20px;font-weight:600">{escape(signature[0])}</span><br>'
              f'<span style="color:#43dfb9;font-size:18px">{escape(self.win_label.text())}</span>　'
              f'<span style="color:#c49af5;font-size:18px">{escape(self.tie_label.text())}</span><br>'
              f'<span style="font-size:13px">{escape(signature[1].replace("目前下注","當時下注").replace("目前底池","當時底池"))}</span>')
        self._last_advice={'signature':signature,'text':text}

    def _show_previous(self,snapshot):
        self.previous_label.setText(snapshot['text'])
        self._fit_previous()

    def _fit_previous(self):
        height=max(110,self.previous_label.heightForWidth(max(100,self.previous_label.width())))
        if self.previous_label.height()!=height:self.previous_label.setFixedHeight(height)

    def eventFilter(self,watched,event):
        if watched is getattr(self,'previous_label',None) and event.type()==QEvent.Resize:
            self._fit_previous()
        return super().eventFilter(watched,event)

    def unavailable_sizing(self,message):
        if '底牌' in message or '尚未發牌' in message:return '目前下注：等待發牌，底牌尚未確認'
        if '輪到' in message or '回合' in message:return '目前下注：尚未確認輪到自己'
        fields=[label for words,label in ((('跟注','call'),'跟注金額'),(('底池',),'底池金額'),(('籌碼','大盲數'),'剩餘大盲數'),(('下注額',),'各座下注')) if any(word in message for word in words)]
        if fields:return '目前下注：尚未確認'+'、'.join(fields)
        if '逾期' in message:return '目前下注：畫面資料已逾期，等待新資料'
        if '背景計算' in message:return '目前下注：正在依新資料計算'
        return '目前下注：'+message.split('\n')[0]

    def begin_refresh(self,same_context=False):
        if same_context:
            self.issue_label.setText('資料狀態：背景更新中\n完成後直接替換目前結果。')
        else:
            self.invalidate('狀態已更新，背景計算中…')

    def enable_fixed_layout(self):
        self.fixed_layout=True
        self.layout().setSpacing(10)
        self.layout().setAlignment(Qt.Alignment())
        for widget in (self.action_label,self.probabilities,self.issue_label,self.sizing_label,self.card_strip,self.summary_scroll):
            policy=widget.sizePolicy()
            policy.setRetainSizeWhenHidden(True)
            widget.setSizePolicy(policy)
        self.action_label.setFixedHeight(90)
        self.probabilities.setFixedHeight(110)
        self.issue_label.setFixedHeight(82)
        self.sizing_label.setFixedHeight(52)
        self.card_strip.setFixedHeight(88)
        if self.dark_theme:
            self.summary_scroll.setMinimumHeight(70)
            self.summary_scroll.setMaximumHeight(16777215)
            self.summary_scroll.auto_height=True
            self.summary_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        else:
            self.summary_scroll.setFixedHeight(70)
        policy=self.summary_scroll.sizePolicy()
        policy.setRetainSizeWhenHidden(False)
        self.summary_scroll.setSizePolicy(policy)
        self.summary_scroll.hide()
        self._fit_previous()

    def resizeEvent(self,event):
        if hasattr(self,'previous_label'):self._fit_previous()
        if self.dark_theme and self.fixed_layout:
            scale=max(.75,min(1.3,self.width()/700,self.window().height()/960))
            self._view_scale=scale
            self.action_label.setFixedHeight(round(70*scale))
            self.probabilities.setFixedHeight(round(80*scale))
            self.issue_label.setFixedHeight(round(68*scale))
            self.sizing_label.setFixedHeight(round(48*scale))
            self.layout().setSpacing(round(3*scale))
            self.apply_display_options(self.display_options)
        wide=self.dark_theme and self.width()>=800
        self.summary_layout.setDirection(QBoxLayout.LeftToRight if wide else QBoxLayout.TopToBottom)
        for index,stretch in enumerate((1,1,0) if wide else (0,0,1)):
            self.summary_layout.setStretch(index,stretch)
        for label in (self.hero_picture,self.board_picture):
            original=label.property('original_cards')
            if original is not None:
                label.setPixmap(original.scaledToHeight(100 if wide else 72,Qt.SmoothTransformation))
        super().resizeEvent(event)

    def render(self, result):
        money=lambda value,signed=False:format_amount(value,result.get('amount_unit','籌碼'),signed)
        if not result.get('equity_only') and 'ev' in result:
            self.last_issue_message=''
        self.issue_label.setVisible(self.fixed_layout)
        if self.fixed_layout:self.issue_label.setText('資料狀態：已確認\n持續追蹤牌桌，資料變動時自動更新。')
        self.sizing_label.show()
        self.summary_scroll.setVisible(not self.fixed_layout)
        hero=result.get('hero_cards',[])
        board=result.get('community_cards',[])
        self.card_strip.setVisible(bool(hero))
        if hero:
            from .threat_matrix import card_names
            self.card_text.setText(f'底牌已確認：{card_names(hero)}\n公共牌：{card_names(board) or "尚未翻牌"}')
        if len(hero)==2 and not board:
            context=result.get('preflop_context') or {}
            previous=getattr(self,'current_preflop_context',{})
            if not context and result.get('live') and previous.get('hero_cards')==hero:
                context=previous
            self.threat_matrix.render_preflop(context or {'hero_cards':hero})
        else:
            self.threat_matrix.render(hero,board)
        self.clear_threat_pictures()
        self.footer.setVisible(not result.get('live',False))
        self.heading.setVisible(not result.get('live',False))
        self.action_label.setVisible(result.get('live',False))
        self.probabilities.show()
        win=result.get('equity_details',{}).get('win_probability')
        self.win_label.setText(f'勝率 {win:.1%}' if win is not None else '勝率 未提供')
        self.tie_label.setText(f'平手 {result.get("tie_probability",0):.1%}')
        types = result.get('beating_hand_types', [])
        label = result.get('threats_details', {}).get('label', '')
        preflop = '翻牌前' in label
        threats_heading = '最後可能贏你的牌（模擬中看過，不是完整清單）：' if preflop else '現在可能贏你的牌：'
        types_text = '、'.join(t.replace('更高點數或踢腳','同牌型，但點數更大') for t in types) if types else ('這次模擬還沒遇到' if preflop else '這次估算沒有找到，但仍可能平手')
        self.summary.setText(
            f"你現在的牌：{result.get('hand_strength', '還沒成牌')}\n\n"
            f"連平手分錢一起算，平均可拿到底池的：{result.get('equity', 0):.2%}\n\n"
            f"這次跟注至少要有 {result.get('required_equity', result.get('pot_odds', 0)):.2%} 的分錢比例才划算。\n\n"
            f"下一張能讓牌型變好的牌：{result.get('outs', 0)} 張，不一定會贏。"
        )
        self.extra.setText(f"對手合計權益：{result.get('opponent_equity', 0):.2%}　平手機率：{result.get('tie_probability', 0):.2%}\n有效大盲與底池比：{format(result['spr'], '.2f') if result.get('spr') is not None else '無法計算'}　模擬次數：{result.get('simulation_count', 0):,}")
        if 'beating_hand_types' in result:
            self.summary.setText(self.summary.text()+f'\n\n{threats_heading}\n{types_text}')
            self.extra.setText(self.extra.text()+f'\n{label}')
        if result.get('live'):
            self.summary.setStyleSheet('font-size: 19px; padding: 16px; color: #203b50; background: #eff6f3; border-radius: 12px;')
            call = result.get('call_amount', 0)
            ev=result.get('ev')
            pot=result.get('pot')
            borderline=call_ev_near_boundary(ev,pot or 0,call,result.get('simulation_count',0)) or (call>0 and ev is not None and abs(ev)<=result.get('amount_rounding_ev_bound',0))
            win = result.get('equity_details', {}).get('win_probability', 0)
            if call == 0:
                reference = '目前較適合：先過牌。\n現在不用補錢。'
            elif borderline:
                reference=f'需補 {money(call)}；估算接近門檻，暫不判定跟注或棄牌。'
            elif result.get('ev', 0) > 0:
                reference = f'目前較適合：跟注 {money(call)}。\n照目前估算，這次跟注划得來。'
            else:
                reference = f'目前較適合：先棄牌。\n要再補 {money(call)}，照目前估算不划算。'
            if result.get('range_assumed'):
                reference= ('現在不用補錢，可以過牌。' if call==0 else
                    f'只看目前跟注成本：補 {money(call)}，估算'+('接近門檻，暫不判定。' if borderline else '划算。' if result.get('ev',0)>0 else '不划算。'))
                reference+='\n對手手牌範圍尚未從行動確認，不能只靠這個估算決定棄牌。'
            guide=result.get('starting_hand',{})
            if guide:
                reference=f'起手牌：{guide["level"]}\n{guide["advice"]}\n\n'+reference
            if result.get('stack_unknown'):
                reference += '\n還看不清楚對手剩多少大盲，先不建議加注多少。'
            elif call == 0:
                scenarios = result.get('bet_scenarios', [])
                half = next((row for row in scenarios if row.get('percentage')==50), None)
                if half:
                    reference += f'\n下注試算：半個底池 {money(half["bet"])}。\n只假設一人跟注，還沒確認這個金額能否加注。'
            precision = '先給你大概結果，正在算得更準。' if result.get('simulation_count',0)<result.get('target_simulations',50000) else '已完成這輪估算。'
            stage = result.get('street', '')
            threat_note = '這是最後發完牌的模擬結果。' if preflop else '只看桌上已經開出的牌。'
            action='過牌' if call==0 else '等待確認｜估算接近門檻' if borderline else f'跟注 {money(call)}（成本估算）' if result.get('ev',0)>0 else f'暫不跟注（需補 {money(call)}）'
            ratio=('｜目前底池 '+format(call/pot,'.1%' if result.get('amount_unit')=='BB' else '.0%')) if pot and pot>0 else '｜底池待確認'
            if call>0 and borderline:
                sizing=f'目前下注：需補 {money(call)}{ratio}｜估算接近門檻，暫不判定'
            elif call>0 and ev is not None and ev>0:
                sizing=f'目前下注：跟注 {money(call)}{ratio}｜依設定的對手範圍估算'
            elif call>0:
                sizing=f'目前下注：需補 {money(call)}{ratio}｜加注尺寸尚未確認'
            else:
                sizing='目前下注：可過牌｜加注尺寸待確認（位置、前面行動及合法尺寸）'
            self.sizing_label.setText(sizing)
            if call==0:
                self.set_action('過牌｜不用補錢','#1765aa')
            elif borderline:
                self.set_action('等待確認｜估算接近邊界','#9a6500')
            elif ev>0:
                self.set_action(f'依估算建議跟注 {money(call)}' if result.get('range_assumed') else f'入場：跟注 {money(call)}','#087d55')
            elif result.get('range_assumed'):
                self.set_action(f'依估算建議棄牌｜需跟注 {money(call)}','#c42b36')
            else:
                self.set_action('不入場：棄牌','#c42b36')
            self.action_label.setToolTip('依目前辨識資料與假設對手範圍的跟注期望值；未納入後續下注、行動位置及完整獎金結構。')
            # 只使用現有跟注成本模型，不把起手牌圖顏色當作期望值。
            entry=('可免費看牌' if call==0 else '待確認' if ev is None else
                '邊界，先確認' if borderline else '可考慮入場' if ev>0 else '暫不投入')
            ev_text='待確認' if ev is None else f'{money(ev,True)}'
            if call==0:
                ev_text='無需跟注'
            entry+=f'｜跟注期望值 {ev_text}'
            raise_text='加注：合法金額待確認'
            if result.get('stack_unknown'):
                raise_text='加注：對手大盲數待確認'
            elif call==0 and result.get('equity',0)>=.6:
                half=next((row for row in result.get('bet_scenarios',[]) if row.get('percentage')==50),None)
                if half and half['bet']<=result.get('effective_stack',0):
                    raise_text=f'下注試算 {money(half["bet"])}｜合法下限待確認'
            self.summary.setText(f'行動參考：{action}\n進場：{entry}\n{raise_text}')
            assumption='｜對手範圍是假設' if result.get('range_assumed') else ''
            if assumption:
                self.summary.setText(self.summary.text()+assumption)
            if guide and result.get('street')=='翻牌前':
                opening={
                    '強起手牌':'未有人加注時可考慮開池；須看位置',
                    '中等口袋對子':'未有人加注時可考慮開池；須看位置與加注',
                    '小口袋對子':'後位、深大盲數可考慮開池；避免跟大注',
                    '大點數起手牌':'中後位可考慮開池；須看位置與加注',
                    '同花發展型起手牌':'後位可考慮開池；避免跟大注',
                }.get(guide['level'],'起手牌偏弱；先看位置與前面加注')
                self.summary.setText(f'起手牌：{guide["level"]}｜{opening}\n行動參考：需補 {money(call)}｜跟注期望值 {ev_text}{assumption}\n{raise_text}')
            chart=guide.get('entry_chart',{}) if result.get('street')=='翻牌前' else {}
            if chart:
                cost=('不用補錢；加注條件待確認' if call==0 else
                    '跟注估算待確認' if borderline else
                    f'依估算建議跟注 {money(call)}' if ev>0 else f'依估算建議棄牌｜需跟注 {money(call)}')
                color='#1765aa' if call==0 else '#9a6500' if borderline else '#087d55' if ev>0 else '#c42b36'
                self.set_action('過牌｜不用補錢' if call==0 else cost,color)
                self.summary.setText(f'使用者牌表：{chart["color"]}｜{chart["rule"]}\n行動參考：{cost}｜跟注期望值 {ev_text}{assumption}\n位置與前面加注待確認；{raise_text}')
            elif self.dark_theme:
                self.summary.setText('行動參考：依目前牌面與跟注成本估算。\n'+
                    ('對手範圍是假設；位置與加注歷史待確認。' if result.get('range_assumed') else '加注建議：合法尺寸與行動歷史待確認。'))
            self.summary.setStyleSheet('font-size: 20px; padding: 8px; color: #203b50; background: #eff6f3; border-radius: 8px;')
            self.extra.setText(self.extra.text()+f'\n{reference}\n{threat_note}\n{precision}')
            self.extra.setText(self.extra.text()+'\n跟注期望值與輸入使用相同單位，公式為分池權益×（目前底池＋跟注差額）－跟注差額。假設不再有後續下注；不是完整策略的行動期望值，接近零時不能忽略模擬與範圍誤差。')
            self.extra.setText(self.extra.text()+f'\n含平手分池權益：{result.get("equity",0):.1%}　跟注所需權益：{result.get("required_equity",0):.1%}\n跟注期望值：{money(result.get("ev",0),True)}\n各對手範圍分別列舉，未驗證多人同時可行；不是牌型出現機率。')
            if guide:
                self.extra.setText(self.extra.text()+f'\n{guide["context"]}\n起手牌資料來源：{guide["source"]}')
                published=guide.get('published_reference',{})
                if published:
                    text=f'公開起手牌參考：對一位隨機對手的含分池權益 {published["random_equity"]:.1%}'
                    if 'range_equity' in published:
                        text+=f'；對目前假設範圍的單挑參考 {published["range_equity"]:.1%}'
                    self.extra.setText(self.extra.text()+f'\n{text}\n{published["label"]}。{published["context"]}\n來源：{published["source"]}；資料版本：{published["source_commit"]}；授權：{published["license"]}')
                    self.summary.setText(self.summary.text()+f'\n起手牌基準：隨機單挑含分池 {published["random_equity"]:.1%}（非本手勝率）')
        if result.get('live') and result.get('facing_all_in') and not result.get('equity_only'):
            call=result.get('call_amount',0)
            ev=result.get('ev')
            needed=result.get('required_equity',result.get('pot_odds',0))
            if call==0:
                self.set_action('對手全下｜目前不用補錢','#1765aa')
            elif borderline:
                self.set_action('對手全下｜估算接近邊界，暫不判定','#9a6500')
            elif ev>0:
                self.set_action(f'對手全下｜依估算建議跟注 {money(call)}','#087d55')
            else:
                self.set_action(f'對手全下｜依估算建議棄牌','#c42b36')
            self.sizing_label.setText(f'目前下注：需補 {money(call)}｜跟注門檻 {needed:.1%}｜依設定的對手範圍估算')
            self.summary.setText('行動參考：依目前跟注成本估算；尚未計入後續下注、邊池及獎金結構。')
        self.mode_notice.clear()
        self.mode_notice.hide()
        if result.get('equity_only'):
            self.show_issue(self.last_issue_message or '下注金額尚未確認')
            self.set_action('勝率已估算｜等待資料確認','#9a6500')
            self.sizing_label.setText(self.unavailable_sizing(self.last_issue_message or '下注金額尚未確認'))
            self.summary.setText(f'目前牌型：{result.get("hand_strength","")}｜對手 {result.get("opponents",0)} 人\n依假設對手範圍估算勝率，金額確認後再分析跟注成本。')
            self.extra.setText(f'快速估算 {result.get("simulation_count",0):,} 次；對手範圍是假設。未使用未知金額計算期望值。')
        if result.get('live') and not result.get('equity_only') and 'hero_turn' in result and result['hero_turn'] is not True:
            self.set_action('等待對手行動' if result['hero_turn'] is False else '確認自身回合｜暫停行動建議','#9a6500')
            self.sizing_label.setText('目前下注：等待輪到自己；勝率持續更新')
        self.threat_pictures.setVisible('threats_details' in result)
        examples=result.get('threats_details',{}).get('visual_examples',[])
        if examples:
            stage=result.get('street','目前公共牌')
            title=QLabel(f'{stage}｜能贏你的牌型（範例）')
            title.setWordWrap(True)
            self.threat_layout.addWidget(title,0,0,1,2)
            for index,example in enumerate(examples):
                tile=QWidget()
                tile_layout=QVBoxLayout(tile)
                tile_layout.setContentsMargins(2,2,2,2)
                category=QLabel(example['category'].replace('更高點數或踢腳','同牌型，但點數更大'))
                category.setWordWrap(True)
                category.setStyleSheet('font-size: 16px; font-weight: bold; color: '+('#f5bf67' if self.dark_theme else '#a13e25')+';')
                tile_layout.addWidget(category)
                picture=QLabel()
                picture.setPixmap(hand_picture(example['hole_cards'],example['best_five']).copy(0,22,110,68))
                picture.setProperty('original_picture',picture.pixmap())
                picture.setToolTip('可組成五張牌：'+'、'.join(example['best_five']))
                tile_layout.addWidget(picture)
                self.threat_layout.addWidget(tile,1+index//2,index%2)
            note=QLabel('對手底牌範例；不是已知持牌。')
            note.setWordWrap(True)
            self.threat_layout.addWidget(note,1+(len(examples)+1)//2,0,1,2)
        elif result.get('live') and 'threats_details' in result:
            title=QLabel(f'{threats_heading}\n{types_text}')
            title.setWordWrap(True)
            self.threat_layout.addWidget(title,0,0,1,2)
        scenarios = result.get('bet_scenarios', [])
        self.scenarios.setRowCount(len(scenarios))
        for row, scenario in enumerate(scenarios):
            values = [f"{scenario.get('percentage', 0)}%",
                      f"{money(scenario.get('bet', scenario.get('bet_amount', 0)))}",
                      f"{money(scenario.get('new_pot', 0))}",
                      f"{scenario.get('required_equity', 0):.2%}",
                      format(scenario['spr'], '.2f') if scenario.get('spr') is not None else '無法計算', f"{money(scenario.get('ev', 0))}"]
            for column, value in enumerate(values):
                self.scenarios.setItem(row, column, QTableWidgetItem(value))
        self.apply_display_options(self.display_options)

    def clear_threat_pictures(self):
        while self.threat_layout.count():
            item=self.threat_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def set_action(self,text,color):
        role={'#087d55':'call_color','#c42b36':'fold_color','#1765aa':'check_color','#9a6500':'wait_color'}.get(color)
        color=self.display_options.get(role,color)
        if self.dark_theme:
            from .theme import accent
            color=accent(color)
        self.action_label.setText(text)
        self.action_label.setProperty('role_color',role)
        self.action_label.setToolTip(text)
        size=round(self.display_options.get('action_font',30)*self._view_scale)
        background=COLORS['card'] if self.dark_theme else '#ffffff'
        self.action_label.setStyleSheet(card_style("#FFFFFF" if role=="wait_color" else color,size,True,True) if self.dark_theme else
            f'font-size:{size}px;font-weight:500;color:{color};background:{background};padding:14px;border:1px solid {color};border-radius:16px;')

    def apply_display_options(self,options):
        self.display_options=dict(options)
        self.threat_matrix.apply_colors(options.get('matrix_background','#00cc66'),options.get('matrix_winner','#ef4444'))
        self.threat_matrix.apply_preflop_colors(options)
        font=round(options.get('probability_font',32)*self._view_scale)
        self.win_label.setStyleSheet(f'font-size: {font}px; font-weight: bold; color: {options.get("win_color","#087d55")}; background: #e5f6ee; padding: 10px;')
        self.tie_label.setStyleSheet(f'font-size: {font}px; font-weight: bold; color: {options.get("tie_color","#7045b4")}; background: #f0eafa; padding: 10px;')
        self.summary.setStyleSheet(f'font-size: {options.get("text_font",20)}px; padding: 8px; color: #203b50; background: #eff6f3; border-radius: 8px;')
        if self.dark_theme:
            from .theme import accent
            self.win_label.setStyleSheet(card_style(COLORS['win'] if options.get('win_color','#087d55') in ('#087d55','#43dfb9') else options['win_color'],font,True,True))
            self.tie_label.setStyleSheet(card_style(accent(options.get('tie_color','#7045b4')),font,True))
            self.summary.setStyleSheet(card_style(COLORS['text'],max(13,round(options.get('text_font',20)*self._view_scale*.8))))
            self.sizing_label.setStyleSheet(card_style(COLORS['text'],max(13,round(16*self._view_scale))).replace('padding:14px','padding:7px 12px'))
            self.issue_label.setStyleSheet(card_style(COLORS['text'],max(13,round(15*self._view_scale))).replace('padding:14px','padding:7px 12px'))

        role=self.action_label.property('role_color')
        default={'call_color':'#087d55','fold_color':'#c42b36','check_color':'#1765aa','wait_color':'#9a6500'}.get(role,'#9a6500')
        self.set_action(self.action_label.text(),default)
        self.threat_pictures.setVisible(options.get('show_threats',True) and self.threat_layout.count()>0)
        self.threat_matrix.setVisible(options.get('show_threats',True))
        for label in self.threat_pictures.findChildren(QLabel):
            original=label.property('original_picture')
            if original is not None:
                label.setPixmap(original.scaledToWidth(round(original.width()*options.get('picture_scale',100)/100),Qt.SmoothTransformation))

    def render_card_threats(self,result,message):
        self.render(dict(result,live=True))
        self.probabilities.setVisible(self.fixed_layout)
        if self.fixed_layout:
            self.win_label.setText('勝率 更新中')
            self.tie_label.setText('平手 更新中')
        self.set_action('等待確認','#9a6500')
        self.summary.setText(message.split('\n')[0])
        self.sizing_label.setText('下注建議：金額未確認，暫停建議尺寸')
        self.extra.setText('此處只比較已確認牌面，不需要下注金額。範例從所有合法對手底牌列舉，不代表實際持牌。')
        self.show_issue(self.last_issue_message or message)

    def show_issue(self,message):
        problem=message.split('\n')[0].removeprefix('資料不確定，請確認：')
        if '校準' in message or '辨識位置設定' in message:
            solution='到「調整設定 → 辨識位置」重新框選，驗證後鎖定。'
        elif '等待牌桌' in message or '找不到' in message:
            solution='開啟牌桌；需要指定牌桌時，到「調整設定 → 辨識位置」選擇。'
        elif '最小化' in message:
            solution='還原牌桌視窗，程式會自動重新讀取。'
        elif '休息' in message or '沒有可見底牌' in message or '尚未發牌' in message:
            solution='等待下一手發牌；目前不提供下注建議。'
        elif '背景計算' in message or '正在確認牌面' in message:
            solution='正在自動處理，完成後會更新，不需要操作。'
        elif '牌背' in message or '持牌' in message:
            solution='等待牌背動畫結束；若持續出現，放大牌桌並確認選對牌桌。'
        elif '金額' in message or '下注' in message or '籌碼' in message or '跟注' in message or '底池' in message:
            solution='等待下注動畫結束；若仍讀不到，放大牌桌並切換成大盲數顯示。'
        elif '底牌' in message or '牌面' in message:
            solution='等待發牌動畫結束；若仍未確認，放大牌桌並檢查是否有遊戲內視窗遮住牌。'
        else:
            solution='確認牌桌仍開啟；持續讀不到時，到「調整設定 → 辨識位置」重新校準。'
        self.issue_label.setText(f'目前問題：{problem}\n解決方式：{solution}')
        self.issue_label.show()
        if self.fixed_layout:
            self.set_action('行動建議：等待底牌確認' if '底牌' in message else '行動建議：等待資料確認','#9a6500')
            self.sizing_label.setText(self.unavailable_sizing(message))
            self.summary.setText('分析說明：資料不確定，確認後自動更新。')
            self.action_label.show()
            self.sizing_label.show()
            self.summary_scroll.hide()
        else:
            self.action_label.hide()
            self.sizing_label.hide()
            self.summary_scroll.hide()

    def invalidate(self, message):
        if self._last_advice:
            self._show_previous(self._last_advice)
        self.reminder_timer.stop()
        self._end_reminder()
        self.last_issue_message=message
        self.mode_notice.clear()
        if not self.fixed_layout:
            self.threat_matrix.render([],[])
        else:
            self.threat_matrix.invalidate()
        self.hero_picture.clear()
        self.board_picture.clear()
        self.sizing_label.setText('下注建議：資料未確認，暫停建議金額')
        self.action_label.show()
        self.set_action('等待確認','#9a6500')
        reasons=(('跟注額','跟注金額'),('自身籌碼','自己的大盲數'),('自身大盲數','自己的大盲數'),('底池','底池'),
            ('底牌','底牌'),('牌面','牌面'),('持牌','持牌人數'),('下注額','各座下注'),('視窗','牌桌視窗'))
        missing=[label for keyword,label in reasons if keyword in message]
        if missing:
            self.set_action('等待確認：'+'、'.join(dict.fromkeys(missing)),'#9a6500')
        self.probabilities.hide()
        self.clear_threat_pictures()
        if '牌面不完整或匹配不足' in message:
            message='有牌還沒看清楚，正在重新讀取。\n\n看清楚後會自動更新，不用按按鈕。'
        elif '牌背或頭像不清楚' in message:
            message='還看不清楚有幾個人拿著牌，正在確認。\n\n確認後會自動更新，不用按按鈕。'
        elif '金額不一致' in message and '：' not in message:
            message='桌上的金額還對不起來。\n\n等金額確認後，再告訴你怎麼做。'
        self.summary.setText(message.split('\n')[0])
        self.extra.clear()
        self.scenarios.setRowCount(0)
        self.card_strip.hide()
        self.show_issue(message)
        if self.fixed_layout:
            self.win_label.setText('勝率 更新中')
            self.tie_label.setText('平手 更新中')
            self.probabilities.show()
            if any(word in message for word in ('等待牌桌','擷取','視窗','休息')):
                self.card_text.setText('底牌與公共牌：正在確認最新資料')
            self.card_strip.show()
