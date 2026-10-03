from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QTableWidget, QTableWidgetItem, QCheckBox, QScrollArea,QBoxLayout
from .hand_picture import hand_picture


class AnalysisPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.display_options={}
        self.dark_theme=False
        layout = QVBoxLayout(self)
        heading = QLabel('分析結果')
        heading.setStyleSheet('font-size: 20px; font-weight: bold; color: #203b50;')
        layout.addWidget(heading)
        self.probabilities=QWidget()
        probabilities_layout=QHBoxLayout(self.probabilities)
        self.win_label=QLabel()
        self.tie_label=QLabel()
        self.win_label.setStyleSheet('font-size: 32px; font-weight: bold; color: #087d55; background: #e5f6ee; padding: 10px;')
        self.tie_label.setStyleSheet('font-size: 32px; font-weight: bold; color: #7045b4; background: #f0eafa; padding: 10px;')
        probabilities_layout.addWidget(self.win_label)
        probabilities_layout.addWidget(self.tie_label)
        layout.addWidget(self.probabilities)
        self.probabilities.hide()
        self.action_label=QLabel('等待確認')
        self.action_label.setWordWrap(True)
        layout.addWidget(self.action_label)
        self.set_action('等待確認','#9a6500')
        layout.removeWidget(self.action_label)
        layout.insertWidget(1,self.action_label)
        self.sizing_label=QLabel('下注建議：等待可靠牌桌資料')
        self.sizing_label.setWordWrap(True)
        self.sizing_label.setStyleSheet('font-size:17px;padding:10px;')
        layout.addWidget(self.sizing_label)
        self.card_strip=QWidget()
        self.card_strip.setObjectName('surfacePanel')
        card_layout=QHBoxLayout(self.card_strip)
        self.hero_picture=QLabel()
        self.board_picture=QLabel()
        for text,picture in (('我的手牌',self.hero_picture),('公共牌',self.board_picture)):
            group=QVBoxLayout()
            caption=QLabel(text)
            caption.setObjectName('sectionTitle')
            group.addWidget(caption)
            group.addWidget(picture)
            card_layout.addLayout(group)
        layout.addWidget(self.card_strip)
        self.card_strip.hide()
        self.summary = QLabel('選好牌、填好金額後，按「分析」。')
        self.summary.setWordWrap(True)
        self.summary.setAlignment(Qt.AlignTop|Qt.AlignLeft)
        self.summary.setStyleSheet('font-size: 23px; padding: 20px; color: #203b50; background: #eff6f3; border-radius: 12px;')
        self.summary_scroll = QScrollArea()
        self.summary_scroll.setWidgetResizable(True)
        self.summary_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.summary_body=QWidget()
        summary_layout=QVBoxLayout(self.summary_body)
        self.summary_layout=summary_layout
        summary_layout.addWidget(self.summary)
        self.threat_pictures=QWidget()
        self.threat_pictures.setObjectName('surfacePanel')
        self.threat_layout=QGridLayout(self.threat_pictures)
        summary_layout.addWidget(self.threat_pictures)
        summary_layout.addStretch()
        self.summary_scroll.setWidget(self.summary_body)
        self.summary_scroll.setMinimumHeight(140)
        layout.addWidget(self.summary_scroll,1)
        self.details_toggle = QCheckBox('查看詳細數據與下注情境')
        layout.addWidget(self.details_toggle)
        self.details = QWidget()
        details_layout = QVBoxLayout(self.details)
        self.extra = QLabel()
        self.extra.setWordWrap(True)
        details_layout.addWidget(self.extra)
        self.scenarios = QTableWidget(0, 6)
        self.scenarios.setHorizontalHeaderLabels(['底池比例', '下注額', '被跟注後底池', '對手所需勝率', '剩餘籌碼底池比', '期望值'])
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

    def resizeEvent(self,event):
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
        hero=result.get('hero_cards',[])
        board=result.get('community_cards',[])
        self.card_strip.setVisible(bool(hero))
        for label,cards in ((self.hero_picture,hero),(self.board_picture,board)):
            label.clear()
            label.setProperty('original_cards',None)
            if cards:
                original=hand_picture(cards,[]).copy(0,20,len(cards)*55,72)
                label.setProperty('original_cards',original)
                label.setPixmap(original.scaledToHeight(100 if self.dark_theme and self.width()>=800 else 72,Qt.SmoothTransformation))
            else:
                label.setText('公共牌尚未開出')
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
        self.extra.setText(f"對手合計權益：{result.get('opponent_equity', 0):.2%}　平手機率：{result.get('tie_probability', 0):.2%}\n籌碼底池比：{format(result['spr'], '.2f') if result.get('spr') is not None else '無法計算'}　模擬次數：{result.get('simulation_count', 0):,}")
        if 'beating_hand_types' in result:
            self.summary.setText(self.summary.text()+f'\n\n{threats_heading}\n{types_text}')
            self.extra.setText(self.extra.text()+f'\n{label}')
        if result.get('live'):
            self.summary.setStyleSheet('font-size: 19px; padding: 16px; color: #203b50; background: #eff6f3; border-radius: 12px;')
            call = result.get('call_amount', 0)
            win = result.get('equity_details', {}).get('win_probability', 0)
            if call == 0:
                reference = '目前較適合：先過牌。\n現在不用補錢。'
            elif result.get('ev', 0) > 0:
                reference = f'目前較適合：跟注 {call:,.0f}。\n照目前估算，這次跟注划得來。'
            else:
                reference = f'目前較適合：先棄牌。\n要再補 {call:,.0f}，照目前估算不划算。'
            if result.get('range_assumed'):
                reference= ('現在不用補錢，可以過牌。' if call==0 else
                    f'只看目前跟注成本：補 {call:,.0f}，估算'+('划算。' if result.get('ev',0)>0 else '不划算。'))
                reference+='\n對手手牌範圍尚未從行動確認，不能只靠這個估算決定棄牌。'
            guide=result.get('starting_hand',{})
            if guide:
                reference=f'起手牌：{guide["level"]}\n{guide["advice"]}\n\n'+reference
            if result.get('stack_unknown'):
                reference += '\n還看不清楚對手剩多少籌碼，先不建議加注多少。'
            elif call == 0:
                scenarios = result.get('bet_scenarios', [])
                half = next((row for row in scenarios if row.get('percentage')==50), None)
                if half:
                    reference += f'\n下注試算：半個底池 {half["bet"]:,.0f}。\n只假設一人跟注，還沒確認這個金額能否加注。'
            precision = '先給你大概結果，正在算得更準。' if result.get('simulation_count',0)<result.get('target_simulations',50000) else '已完成這輪估算。'
            stage = result.get('street', '')
            threat_note = '這是最後發完牌的模擬結果。' if preflop else '只看桌上已經開出的牌。'
            action='過牌' if call==0 else f'跟注 {call:,.0f}（成本估算）' if result.get('ev',0)>0 else f'暫不跟注（需補 {call:,.0f}）'
            ev=result.get('ev')
            pot=result.get('pot')
            ratio=f'｜目前底池 {call/pot:.0%}' if pot and pot>0 else '｜底池待確認'
            if call>0 and ev is not None and ev>0:
                sizing=f'跟注參考：補 {call:,.0f}{ratio}。依目前對手範圍估算。'
            elif call>0:
                sizing=f'需補 {call:,.0f}{ratio}。加注建議：位置與加注歷史待確認。'
            else:
                sizing='下注建議：位置、前面行動與合法尺寸待確認；目前不需補錢。'
            self.sizing_label.setText(sizing)
            if call==0:
                self.set_action('過牌｜不用補錢','#1765aa')
            elif ev is None or abs(ev)<1:
                self.set_action('等待確認｜估算接近邊界','#9a6500')
            elif ev>0:
                self.set_action(f'估算可跟注 {call:,.0f}' if result.get('range_assumed') else f'入場：跟注 {call:,.0f}','#087d55')
            elif result.get('range_assumed'):
                self.set_action('跟注成本偏高｜先確認對手加注','#9a6500')
            else:
                self.set_action('不入場：棄牌','#c42b36')
            self.action_label.setToolTip('依目前辨識資料與假設對手範圍的跟注期望值；未納入後續下注、行動位置及完整獎金結構。')
            # 只使用現有跟注成本模型，不把起手牌圖顏色當作期望值。
            entry=('可免費看牌' if call==0 else '待確認' if ev is None else
                '邊界，先確認' if abs(ev)<1 else '可考慮入場' if ev>0 else '暫不投入')
            ev_text='待確認' if ev is None else f'{ev:+,.0f}'
            if call==0:
                ev_text='無需跟注'
            entry+=f'｜跟注期望值 {ev_text}'
            raise_text='加注：合法金額待確認'
            if result.get('stack_unknown'):
                raise_text='加注：對手籌碼待確認'
            elif call==0 and result.get('equity',0)>=.6:
                half=next((row for row in result.get('bet_scenarios',[]) if row.get('percentage')==50),None)
                if half and half['bet']<=result.get('effective_stack',0):
                    raise_text=f'下注試算 {half["bet"]:,.0f}｜合法下限待確認'
            self.summary.setText(f'行動參考：{action}\n進場：{entry}\n{raise_text}')
            assumption='｜對手範圍是假設' if result.get('range_assumed') else ''
            if assumption:
                self.summary.setText(self.summary.text()+assumption)
            if guide and result.get('street')=='翻牌前':
                opening={
                    '強起手牌':'未有人加注時可考慮開池；須看位置',
                    '中等口袋對子':'未有人加注時可考慮開池；須看位置與加注',
                    '小口袋對子':'後位、深籌碼可考慮開池；避免跟大注',
                    '大點數起手牌':'中後位可考慮開池；須看位置與加注',
                    '同花發展型起手牌':'後位可考慮開池；避免跟大注',
                }.get(guide['level'],'起手牌偏弱；先看位置與前面加注')
                self.summary.setText(f'起手牌：{guide["level"]}｜{opening}\n行動參考：需補 {call:,.0f}｜跟注期望值 {ev_text}{assumption}\n{raise_text}')
            chart=guide.get('entry_chart',{}) if result.get('street')=='翻牌前' else {}
            if chart:
                cost=('不用補錢；加注條件待確認' if call==0 else
                    '跟注估算待確認' if ev is None or abs(ev)<1 else
                    f'估算可跟注 {call:,.0f}' if ev>0 else f'跟注成本偏高 {call:,.0f}')
                color={'藍色':'#087d55','黃色':'#9a6500','灰色':'#c42b36'}[chart['color']]
                self.set_action(f'{chart["rule"]}｜{cost}',color)
                self.summary.setText(f'使用者牌表：{chart["color"]}｜{chart["rule"]}\n行動參考：{cost}｜跟注期望值 {ev_text}{assumption}\n位置與前面加注待確認；{raise_text}')
            elif self.dark_theme:
                self.summary.setText('行動參考：依目前牌面與跟注成本估算。\n'+
                    ('對手範圍是假設；位置與加注歷史待確認。' if result.get('range_assumed') else '加注建議：合法尺寸與行動歷史待確認。'))
            self.summary.setStyleSheet('font-size: 20px; padding: 8px; color: #203b50; background: #eff6f3; border-radius: 8px;')
            self.extra.setText(self.extra.text()+f'\n{reference}\n{threat_note}\n{precision}')
            self.extra.setText(self.extra.text()+'\n跟注期望值單位為籌碼，公式為分池權益×（目前底池＋跟注差額）－跟注差額。假設不再有後續下注；不是完整策略的行動期望值，接近零時不能忽略模擬與範圍誤差。')
            self.extra.setText(self.extra.text()+f'\n含平手分池權益：{result.get("equity",0):.1%}　跟注所需權益：{result.get("required_equity",0):.1%}\n跟注期望值：{result.get("ev",0):+,.0f}\n各對手範圍分別列舉，未驗證多人同時可行；不是牌型出現機率。')
            if guide:
                self.extra.setText(self.extra.text()+f'\n{guide["context"]}\n起手牌資料來源：{guide["source"]}')
                published=guide.get('published_reference',{})
                if published:
                    text=f'公開起手牌參考：對一位隨機對手的含分池權益 {published["random_equity"]:.1%}'
                    if 'range_equity' in published:
                        text+=f'；對目前假設範圍的單挑參考 {published["range_equity"]:.1%}'
                    self.extra.setText(self.extra.text()+f'\n{text}\n{published["label"]}。{published["context"]}\n來源：{published["source"]}；資料版本：{published["source_commit"]}；授權：{published["license"]}')
                    self.summary.setText(self.summary.text()+f'\n起手牌基準：隨機單挑含分池 {published["random_equity"]:.1%}（非本手勝率）')
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
        elif result.get('live'):
            title=QLabel(f'{threats_heading}\n{types_text}')
            title.setWordWrap(True)
            self.threat_layout.addWidget(title,0,0,1,2)
        scenarios = result.get('bet_scenarios', [])
        self.scenarios.setRowCount(len(scenarios))
        for row, scenario in enumerate(scenarios):
            values = [f"{scenario.get('percentage', 0)}%",
                      f"{scenario.get('bet', scenario.get('bet_amount', 0)):,.2f}",
                      f"{scenario.get('new_pot', 0):,.2f}",
                      f"{scenario.get('required_equity', 0):.2%}",
                      format(scenario['spr'], '.2f') if scenario.get('spr') is not None else '無法計算', f"{scenario.get('ev', 0):,.2f}"]
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
        size=self.display_options.get('action_font',30)
        background='#092c29' if self.dark_theme else '#ffffff'
        self.action_label.setStyleSheet(f'font-size: {size}px; font-weight: bold; color: {color}; background: {background}; padding: 14px; border: 1px solid {color}; border-radius: 10px;')

    def apply_display_options(self,options):
        self.display_options=dict(options)
        font=options.get('probability_font',32)
        self.win_label.setStyleSheet(f'font-size: {font}px; font-weight: bold; color: {options.get("win_color","#087d55")}; background: #e5f6ee; padding: 10px;')
        self.tie_label.setStyleSheet(f'font-size: {font}px; font-weight: bold; color: {options.get("tie_color","#7045b4")}; background: #f0eafa; padding: 10px;')
        self.summary.setStyleSheet(f'font-size: {options.get("text_font",20)}px; padding: 8px; color: #203b50; background: #eff6f3; border-radius: 8px;')
        if self.dark_theme:
            from .theme import accent
            self.win_label.setStyleSheet(f'font-family:"Inter","Noto Sans TC";font-size:{font}px;font-weight:600;color:{accent(options.get("win_color","#087d55"))};background:#101f2c;padding:14px;border:1px solid #263e50;border-radius:10px;')
            self.tie_label.setStyleSheet(f'font-family:"Inter","Noto Sans TC";font-size:{font}px;font-weight:600;color:{accent(options.get("tie_color","#7045b4"))};background:#101f2c;padding:14px;border:1px solid #263e50;border-radius:10px;')
            self.summary.setStyleSheet(f'font-size:{options.get("text_font",20)}px;padding:14px;color:#c6dbe9;background:#101f2c;border:1px solid #263e50;border-radius:10px;')
            self.sizing_label.setStyleSheet('font-size:18px;font-weight:500;padding:14px;color:#f3d8a4;background:#302619;border:1px solid #88632f;border-radius:8px;')
        role=self.action_label.property('role_color')
        default={'call_color':'#087d55','fold_color':'#c42b36','check_color':'#1765aa','wait_color':'#9a6500'}.get(role,'#9a6500')
        self.set_action(self.action_label.text(),default)
        self.threat_pictures.setVisible(options.get('show_threats',True))
        for label in self.threat_pictures.findChildren(QLabel):
            original=label.property('original_picture')
            if original is not None:
                label.setPixmap(original.scaledToWidth(round(original.width()*options.get('picture_scale',100)/100),Qt.SmoothTransformation))

    def render_card_threats(self,result,message):
        self.render(dict(result,live=True))
        self.probabilities.hide()
        self.set_action('等待確認','#9a6500')
        self.summary.setText(message.split('\n')[0])
        self.sizing_label.setText('下注建議：金額未確認，暫停建議尺寸')
        self.extra.setText('此處只比較已確認牌面，不需要下注金額。範例從所有合法對手底牌列舉，不代表實際持牌。')

    def invalidate(self, message):
        self.card_strip.hide()
        self.hero_picture.clear()
        self.board_picture.clear()
        self.sizing_label.setText('下注建議：資料未確認，暫停建議金額')
        self.action_label.show()
        self.set_action('等待確認','#9a6500')
        reasons=(('跟注額','跟注金額'),('自身籌碼','自己的籌碼'),('底池','底池'),
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
