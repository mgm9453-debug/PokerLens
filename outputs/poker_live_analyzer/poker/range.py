"""對手底牌範圍展開及儲存。"""
import json
import re
from itertools import combinations
from pathlib import Path
from .cards import DECK, RANKS, SUITS, validate_cards

PRESETS = {'緊':'AA KK QQ JJ TT AK AQs', '標準':'AA KK QQ JJ TT 99 88 AK AQ AJ ATs KQ KJs QJs', '寬':'AA KK QQ JJ TT 99 88 77 66 55 44 33 22 AK AQ AJ AT A9s A8s A7s A6s A5s A4s A3s A2s KQ KJ KT QJ QT JT T9s 98s 87s 76s 65s'}

def expand_range(expression, blocked=()):
    blocked = set(validate_cards(blocked))
    if isinstance(expression, str):
        expression={'tight':'緊','standard':'標準','loose':'寬'}.get(expression,expression)
        expression = PRESETS.get(expression, expression)
        tokens = [t for t in re.split(r'[\s,，]+', expression.strip()) if t]
        hands = set()
        for token in tokens:
            if len(token) == 4 and token[:2] in DECK:
                pair = validate_cards([token[:2], token[2:]])
                hands.add(tuple(sorted(pair)))
                continue
            if not re.fullmatch(r'[2-9TJQKA]{2}[so]?', token):
                raise ValueError('範圍牌型格式錯誤：' + token)
            a, b = token[:2]
            mode = token[2:]
            if a == b:
                if mode: raise ValueError('口袋對子不能指定同花或異花')
                hands.update(tuple(sorted((a+x,a+y))) for x,y in combinations(SUITS,2))
            else:
                hands.update(tuple(sorted((a+x,b+y))) for x in SUITS for y in SUITS if not mode or (mode=='s' and x==y) or (mode=='o' and x!=y))
    else:
        hands = set()
        for hand in expression:
            pair = validate_cards(hand)
            if len(pair) != 2: raise ValueError('每組底牌須有兩張')
            hands.add(tuple(sorted(pair)))
    if not hands: raise ValueError('對手範圍不可為空')
    available = sorted(h for h in hands if not blocked.intersection(h))
    if not available: raise ValueError('對手範圍全部被已知卡牌阻擋')
    return available

def save_range(path, expression):
    expand_range(expression)
    Path(path).write_text(json.dumps({'range':expression}, ensure_ascii=False, indent=2), encoding='utf-8')

def load_range(path):
    expression = json.loads(Path(path).read_text(encoding='utf-8'))['range']
    expand_range(expression)
    return expression
