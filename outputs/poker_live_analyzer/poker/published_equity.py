"""公開翻牌前資料的離線參考；不取代本手勝率、平手率或行動決策。"""
import hashlib
import json
import logging
import math
from collections import Counter
from functools import lru_cache
from app_paths import resource_path
from .cards import RANKS, validate_cards
from .range import expand_range

SOURCE = 'https://github.com/poker-yoga/poker-math'
COMMIT = '8a68401fb2edffb18865673a47eb500150e2b028'
HASHES = {
    'starting-hands-vs-random.json': 'b615d058e2dd1d88d157c913bf65e88c136c72c9561bb38958f40bb7f2f74f69',
    'preflop-equity.json': 'eaecde3e60b7f95eac055010b169e825c67b4ebee1278c36098bbc2c9c8ef9a6',
}


def hand_class(cards):
    cards = validate_cards(cards)
    if len(cards) != 2:
        raise ValueError('需提供兩張底牌')
    a, b = sorted(cards, key=lambda card: RANKS.index(card[0]), reverse=True)
    return a[0]+b[0]+('' if a[0] == b[0] else 's' if a[1] == b[1] else 'o')


@lru_cache(maxsize=1)
def load_tables():
    files = {}
    for name, expected in HASHES.items():
        raw = resource_path('assets/poker_reference').joinpath(name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('公開運算資料完整性驗證失敗')
        files[name] = json.loads(raw)
    reference, matrix = files.values()
    table = {row['hand']: row['equityVsRandom']/100 for row in reference['rows']}
    classes = matrix['classes']
    ranks = 'AKQJT98765432'
    expected_classes = {rank*2 for rank in ranks} | {
        a+b+mode for i, a in enumerate(ranks) for b in ranks[i+1:] for mode in ('s', 'o')}
    if len(classes) != 169 or set(classes) != expected_classes or set(table) != expected_classes:
        raise ValueError('公開起手牌資料不完整')
    if len(matrix['upper']) != 14365 or any(
        not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1
        for value in [*table.values(), *matrix['upper']]
    ):
        raise ValueError('公開權益資料無效')
    return table, matrix


def matchup_equity(hero_class, opponent_class):
    _, matrix = load_tables()
    try:
        a, b = matrix['classes'].index(hero_class), matrix['classes'].index(opponent_class)
    except ValueError as exc:
        raise ValueError('起手牌分類無效') from exc
    reverse = a > b
    a, b = min(a, b), max(a, b)
    value = matrix['upper'][a*169-a*(a-1)//2+b-a]
    return 1-value if reverse else value


def published_reference(cards, board=(), opponent_ranges=()):
    if board:
        return {}
    key = hand_class(cards)
    table, _ = load_tables()
    result = {
        'hand': key, 'random_equity': table[key], 'source': SOURCE,
        'source_commit': COMMIT, 'license': 'CC0-1.0', 'strategy_available': False,
        'samples_per_pair': 1000000,
        'label': '公開翻牌前單挑權益參考（含平手分池、花色平均估計）',
        'context': '基準是假設一位隨機對手；不是目前牌局勝率，也不直接決定進場或下注。',
    }
    if len(opponent_ranges) == 1:
        combos = expand_range(opponent_ranges[0], cards)
        counts = Counter(hand_class(combo) for combo in combos)
        # 只有完整牌型範圍才能使用花色平均表；特定花色或部分組合仍用原本模擬。
        if all(count == len(expand_range(label, cards)) for label, count in counts.items()):
            result['range_equity'] = sum(count*matchup_equity(key, label)
                                         for label, count in counts.items())/len(combos)
            result['range_combos'] = len(combos)
    return result


def optional_reference(cards, board=(), opponent_ranges=()):
    try:
        return published_reference(cards, board, opponent_ranges)
    except (OSError, ValueError, KeyError, TypeError):
        logging.warning('公開起手牌參考無法載入，繼續使用原本牌局運算')
        return {}
