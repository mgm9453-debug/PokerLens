"""標準牌組與卡牌檢查。"""
RANKS = '23456789TJQKA'
SUITS = 'cdhs'
DECK = tuple(r + s for r in RANKS for s in SUITS)

def validate_cards(cards):
    result = list(cards)
    if any(c not in DECK for c in result):
        raise ValueError('卡牌格式錯誤，請使用例如 As、Td 的格式')
    if len(set(result)) != len(result):
        raise ValueError('卡牌重複')
    return result
