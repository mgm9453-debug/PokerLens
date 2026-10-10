from poker.amount_units import state_in_bb
from copy import deepcopy
from uuid import uuid4
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QDialog, QGridLayout, QDoubleSpinBox, QSpinBox, QComboBox,
                              QFormLayout)

SUITS = [('s', '♠'), ('h', '♥'), ('d', '♦'), ('c', '♣')]
RANKS = 'AKQJT98765432'


def card_label(card):
    if not card:
        return '＋'
    return ('10' if card[0] == 'T' else card[0]) + dict(SUITS)[card[1]]


class CardPicker(QDialog):
    def __init__(self, title, unavailable=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.chosen = None
        self.buttons = {}
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('點選一張牌；灰色牌已在其他位置使用。'))
        grid = QGridLayout()
        for row, (suit, symbol) in enumerate(SUITS):
            for column, rank in enumerate(RANKS):
                card = rank + suit
                button = QPushButton(card_label(card))
                button.setMinimumSize(47, 56)
                color = '#c83d4f' if suit in 'hd' else '#233747'
                button.setStyleSheet(f'font-size: 20px; font-weight: bold; color: {color};')
                button.setEnabled(card not in unavailable)
                button.clicked.connect(lambda checked=False, value=card: self.choose(value))
                grid.addWidget(button, row, column)
                self.buttons[card] = button
        layout.addLayout(grid)
        buttons = QHBoxLayout()
        clear = QPushButton('移除此牌')
        clear.clicked.connect(lambda: self.choose(None))
        cancel = QPushButton('取消')
        cancel.clicked.connect(self.reject)
        buttons.addWidget(clear)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

    def choose(self, card):
        self.chosen = card
        self.accept()


class CardButton(QPushButton):
    changed = Signal()

    def __init__(self, title, unavailable, parent=None):
        super().__init__('＋', parent)
        self.card = None
        self.title = title
        self.unavailable = unavailable
        self.setMinimumSize(62, 82)
        self.setToolTip(f'點選{title}')
        self.clicked.connect(self.pick)
        self.set_card(None)

    def set_card(self, card):
        if card is not None and (len(card) != 2 or card[0] not in RANKS or card[1] not in dict(SUITS)):
            raise ValueError('卡牌格式錯誤')
        self.card = card
        self.setText(card_label(card))
        color = '#ca4054' if card and card[1] in 'hd' else '#203b50'
        self.setStyleSheet(f'font-size: 27px; font-weight: bold; background: white; color: {color}; border: 1px solid #cad6de; border-radius: 9px;')
        self.changed.emit()

    def pick(self):
        dialog = CardPicker(self.title, self.unavailable(self), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_card(dialog.chosen)


class SimpleHandForm(QWidget):
    edited = Signal()

    def __init__(self):
        super().__init__()
        self.hand_id = uuid4().hex
        self.base = {'amount_unit':'BB','big_blind':1}
        self.loaded_range_index = 0
        layout = QVBoxLayout(self)
        title = QLabel('① 選牌')
        title.setStyleSheet('font-size: 20px; font-weight: bold;')
        layout.addWidget(title)
        self.hero = []
        self.board = []
        for label, target, count in [('你的底牌', self.hero, 2), ('公共牌（翻牌前留空）', self.board, 5)]:
            layout.addWidget(QLabel(label))
            row = QHBoxLayout()
            for index in range(count):
                button = CardButton(f'{label}第 {index+1} 張', self.unavailable)
                button.changed.connect(self.edited)
                target.append(button)
                row.addWidget(button)
            row.addStretch()
            layout.addLayout(row)
        layout.addSpacing(12)
        money_title = QLabel('② 填金額')
        money_title.setStyleSheet('font-size: 20px; font-weight: bold;')
        layout.addWidget(money_title)
        fields = QFormLayout()
        self.pot = self.money_input()
        self.call = self.money_input()
        self.stack = self.money_input()
        fields.addRow('目前底池（大盲數）', self.pot)
        fields.addRow('需要跟注（大盲數）', self.call)
        fields.addRow('有效大盲數', self.stack)
        self.opponents = QSpinBox()
        self.opponents.setRange(1, 8)
        self.opponents.setMinimumHeight(34)
        self.opponents.valueChanged.connect(self.edited)
        fields.addRow('仍在牌局的對手', self.opponents)
        self.range_choice = QComboBox()
        self.range_choice.addItems(['標準（預設）', '較保守', '較寬', '進階自訂'])
        self.range_choice.model().item(3).setEnabled(False)
        self.range_choice.setMinimumHeight(34)
        self.range_choice.currentIndexChanged.connect(self.edited)
        fields.addRow('對手範圍', self.range_choice)
        layout.addLayout(fields)
        hint = QLabel('底池須包含對手已下注金額。\n有效大盲數是你與對手可共同投入的較小值，所有金額皆以大盲數填寫。')
        hint.setStyleSheet('color: #647987;')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()

    def money_input(self):
        widget = QDoubleSpinBox()
        widget.setRange(0, 1000000000)
        widget.setDecimals(4)
        widget.setSingleStep(.1)
        widget.setSuffix(' BB')
        widget.setGroupSeparatorShown(True)
        widget.setMinimumHeight(34)
        widget.valueChanged.connect(self.edited)
        return widget

    def unavailable(self, selected):
        return {button.card for button in self.hero + self.board if button is not selected and button.card}

    def clear(self):
        self.base = {'amount_unit':'BB','big_blind':1}
        self.hand_id = uuid4().hex
        for button in self.hero + self.board:
            button.set_card(None)
        for field in (self.pot, self.call, self.stack):
            field.setValue(0)
        self.opponents.setValue(1)
        self.range_choice.setCurrentIndex(0)
        self.range_choice.model().item(3).setEnabled(False)
        self.loaded_range_index = 0

    def load_data(self, data):
        data=state_in_bb(data)
        self.base = deepcopy(data)
        self.hand_id = data.get('hand_id') or self.hand_id
        for buttons, values in [(self.hero, data.get('hero_cards', [])),
                                (self.board, data.get('community_cards', data.get('board', [])))]:
            for index, button in enumerate(buttons):
                button.set_card(values[index] if index < len(values) else None)
        self.pot.setValue(data.get('pot', 0))
        self.call.setValue(data.get('call_amount', 0))
        self.stack.setValue(data.get('effective_stack', 0))
        active = [p for p in data.get('players', []) if p['seat'] != data.get('hero_seat') and p.get('active', True) and not p.get('folded', False)]
        self.opponents.setValue(max(1, len(active)))
        values = list(data.get('ranges', {}).values())
        value = values[0] if values else 'standard'
        index = {'standard': 0, '標準': 0, 'tight': 1, '緊': 1, 'loose': 2, '寬': 2}.get(value, 3) if isinstance(value, str) else 3
        if any(item != value for item in values):
            index = 3
        self.range_choice.setCurrentIndex(index)
        self.range_choice.model().item(3).setEnabled(index == 3)
        self.loaded_range_index = index

    def to_data(self):
        hero = [button.card for button in self.hero if button.card]
        board = [button.card for button in self.board if button.card]
        if len(hero) != 2:
            raise ValueError('請先選好兩張底牌')
        if len(board) not in (0, 3, 4, 5):
            raise ValueError('公共牌請選零、三、四或五張')
        if any(not button.card for button in self.board[:len(board)]):
            raise ValueError('公共牌請由左至右依序選擇')
        if len(set(hero + board)) != len(hero + board):
            raise ValueError('同一張牌不能重複使用')
        pot, call, stack = self.pot.value(), self.call.value(), self.stack.value()
        if call > pot:
            raise ValueError('底池須包含對手下注，不能小於需要跟注的金額')
        if call > stack:
            raise ValueError('需要跟注的金額不能超過有效籌碼')
        data = deepcopy(self.base)
        hero_seat = data.get('hero_seat')
        players = deepcopy(data.get('players', []))
        opponents = [p for p in players if p['seat'] != hero_seat and p.get('active', True) and not p.get('folded', False)]
        preserved = any(p['seat'] == hero_seat for p in players) and len(opponents) == self.opponents.value()
        if preserved:
            hero_player = next(p for p in players if p['seat'] == hero_seat)
            hero_player['stack'] = max(hero_player.get('stack', 0), stack)
            if hero_player.get('hole_cards'):
                hero_player['hole_cards'] = list(hero)
            if call != data.get('call_amount', 0):
                opponent = max(opponents, key=lambda p: p.get('current_bet', p.get('bet', 0)))
                previous_bet = opponent.get('current_bet', opponent.get('bet', 0))
                new_bet = hero_player.get('current_bet', hero_player.get('bet', 0)) + call
                if any(p is not opponent and p.get('current_bet', p.get('bet', 0)) > new_bet for p in opponents):
                    raise ValueError('其他對手下注仍較高，請在進階設定修正下注資料')
                opponent['current_bet'] = new_bet
                previous_investment = opponent.get('total_invested') or previous_bet
                opponent['total_invested'] = max(new_bet, previous_investment + new_bet - previous_bet)
        else:
            hero_seat = 1
            players = [{'seat': 1, 'position': '自身', 'stack': stack, 'current_bet': 0,
                        'total_invested': 0, 'action': '等待', 'folded': False}]
            opponents = []
            for index in range(self.opponents.value()):
                bet = call if index == 0 else 0
                opponent = {'seat': index + 2, 'position': f'對手 {index+1}', 'stack': stack,
                            'current_bet': bet, 'total_invested': bet,
                            'action': '下注' if bet else '等待', 'folded': False}
                players.append(opponent)
                opponents.append(opponent)
            data['dealer_position'] = None
            data['dealer_seat'] = None
        ranges = {}
        preset = ['standard', 'tight', 'loose', None][self.range_choice.currentIndex()]
        old_ranges = list(self.base.get('ranges', {}).values())
        for index, opponent in enumerate(opponents):
            seat = opponent['seat']
            if preset is None and not old_ranges:
                raise ValueError('請先在進階設定建立自訂範圍，或改用標準範圍')
            previous_range = self.base.get('ranges', {}).get(str(seat))
            if self.range_choice.currentIndex() == self.loaded_range_index and previous_range is not None:
                ranges[str(seat)] = previous_range
            else:
                ranges[str(seat)] = preset if preset else old_ranges[min(index, len(old_ranges)-1)]
        for player in players:
            player.pop('bet', None)
        data.pop('board', None)
        data.update(hero_cards=hero, community_cards=board, hero_seat=hero_seat,
                    pot=pot, call_amount=call, hero_stack=max(data.get('hero_stack', 0), stack),
                    effective_stack=stack, players=players, ranges=ranges, hand_id=self.hand_id,
                    source='手動', street='', amount_unit='BB',big_blind=1,amount_resolution={})
        if hero != self.base.get('hero_cards', []) or board != self.base.get('community_cards', self.base.get('board', [])):
            data.update(showdown=False, hand_complete=False)
        return data
