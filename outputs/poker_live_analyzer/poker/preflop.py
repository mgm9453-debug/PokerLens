"""翻前位置與已授權範圍的嚴格匹配；缺資料不假定為棄牌。"""
import json
import math
from pathlib import Path

RANKS = 'AKQJT98765432'
CONDITIONS = ('format', 'players', 'stack_bb', 'ante_bb', 'position', 'scenario',
    'open_bb', 'opponent_position', 'ante_type', 'payout_model')


def positions(seats, dealer):
    seats = sorted(set(seats))
    if dealer not in seats or not 2 <= len(seats) <= 9:
        return {}
    start = seats.index(dealer)
    ordered = seats[start:] + seats[:start]
    if len(seats) == 2:
        return dict(zip(ordered, ('BTN/SB', 'BB')))
    early = {3: (), 4: ('CO',), 5: ('HJ', 'CO'), 6: ('UTG', 'HJ', 'CO'),
        7: ('UTG', 'LJ', 'HJ', 'CO'), 8: ('UTG', 'UTG+1', 'LJ', 'HJ', 'CO'),
        9: ('UTG', 'UTG+1', 'UTG+2', 'LJ', 'HJ', 'CO')}[len(seats)]
    return dict(zip(ordered, ('BTN', 'SB', 'BB', *early)))


class PositionTracker:
    def __init__(self):
        self.reset()

    def reset(self):
        self.hero = None
        self.board = ()
        self.seats = ()
        self.dealer = None

    def observe(self, hero, board, occupied, dealer, complete):
        hero, board = tuple(hero), tuple(board)
        if len(hero) != 2:
            self.reset()
            return {'position': None, 'positions': {}, 'players': None}
        if self.hero != hero or (self.board and not board):
            self.reset()
        self.hero, self.board = hero, board
        if not self.seats and complete and dealer in occupied:
            self.seats = tuple(sorted(set(occupied)))
            self.dealer = dealer
        # 同一手的莊家與名單只確認一次；棄牌不改位置。
        mapping = positions(self.seats, self.dealer)
        return {'position': mapping.get(0), 'positions': mapping,
            'players': len(self.seats) if mapping else None, 'dealer_seat': self.dealer}


class RangeBook:
    def __init__(self, entries=()):
        self.entries = []
        valid_hands = {a + b if i == j else a + b + 's' if i < j else b + a + 'o'
            for i, a in enumerate(RANKS) for j, b in enumerate(RANKS)}
        for entry in entries:
            if not isinstance(entry, dict) or any(key not in entry for key in CONDITIONS):
                raise ValueError('範圍缺少完整適用條件')
            if entry['format'] != 'MTT' or type(entry['players']) is not int or not 2 <= entry['players'] <= 9:
                raise ValueError('範圍須為錦標賽與有效人數')
            for key in ('stack_bb', 'ante_bb', 'open_bb'):
                value = entry[key]
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or (key != 'ante_bb' and value == 0):
                    raise ValueError('範圍的籌碼、前注與尺寸不合法')
            if any(not isinstance(entry.get(key), str) or not entry[key].strip()
                    for key in ('source', 'license', 'solver', 'position', 'scenario')):
                raise ValueError('範圍缺少來源、授權或求解條件')
            if entry['scenario'] not in ('open', 'vs_open', 'vs_3bet', 'vs_4bet', 'vs_limp', 'bb_option'):
                raise ValueError('不支援的翻前情境')
            if entry['ante_type'] not in ('none', 'big_blind', 'per_player') or entry['payout_model'] not in ('chip_ev', 'icm'):
                raise ValueError('範圍缺少前注形式或收益模型')
            if not isinstance(entry.get('hands'), dict) or not entry['hands']:
                raise ValueError('範圍牌型資料為空')
            for hand, frequencies in entry['hands'].items():
                if hand not in valid_hands or not isinstance(frequencies, dict) or not frequencies:
                    raise ValueError('無效的牌型或動作頻率')
                if set(frequencies) - {'raise', 'call', 'fold', 'check'}:
                    raise ValueError('未知的策略動作')
                if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in frequencies.values()) or sum(frequencies.values()) > 1 + 1e-9:
                    raise ValueError('動作頻率必須有限且總和不超過百分之百')
            if any(all(old[key] == entry[key] for key in CONDITIONS) for old in self.entries):
                raise ValueError('範圍條件重複')
            self.entries.append(entry)

    @classmethod
    def load(cls, path):
        path = Path(path)
        if not path.is_file():
            return cls()
        if path.stat().st_size > 5_000_000:
            raise ValueError('範圍資料過大')
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, list):
            raise ValueError('範圍資料須為清單')
        return cls(data)

    def match(self, context):
        if any(context.get(key) is None for key in CONDITIONS if key != 'opponent_position'):
            return None
        # 未確認前注或籌碼不以最接近圖表替代。
        candidates=[entry for entry in self.entries
            if all(entry[key] == context.get(key) for key in CONDITIONS)]
        return candidates[0] if len(candidates)==1 else None
