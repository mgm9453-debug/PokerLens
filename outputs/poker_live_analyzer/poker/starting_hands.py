"""根據公開教學整理起手牌參考；不替代位置及下注歷史分析。"""
from .cards import RANKS,validate_cards
from .entry_chart import chart_entry
from .published_equity import optional_reference

SOURCE='https://www.pokerstars.com/poker/learn/strategies/level-up-your-starting-hand-selection/'

def starting_hand_guide(cards,board=()):
    if board or len(cards)!=2: return {}
    validate_cards(cards)
    first,second=sorted(cards,key=lambda c:RANKS.index(c[0]),reverse=True)
    a,b=first[0],second[0]
    suited=first[1]==second[1]
    key=a+b+('' if a==b else 's' if suited else 'o')
    if a==b and a in 'AKQJ' or a+b=='AK' or a+b=='AQ' and suited:
        level='強起手牌'
        advice='如果前面沒有人加注，通常可考慮主動加注；有人加注時，要再看加注大小與籌碼。'
    elif a==b and a in 'T98':
        level='中等口袋對子'
        advice='多數位置可考慮開池加注；前位或面對大加注時要更謹慎。'
    elif a==b:
        level='小口袋對子'
        advice='偏向後位、籌碼較深的情況；主要期待翻牌中三條，不適合只因有對子就跟大注。'
    elif a+b in ('AQ','AJ','KQ','KJ','QJ','JT'):
        level='大點數起手牌'
        advice='中後位、前面沒有加注時較適合考慮開池；同花更有發展性，前位需收緊。'
    elif suited and (a=='A' or abs(RANKS.index(a)-RANKS.index(b)) in (1,2)):
        level='同花發展型起手牌'
        advice='較適合後位、未有人加注時考慮開池；面對大加注不應直接套用。'
    else:
        level='較弱起手牌'
        advice='一般不優先投入；能免費看翻牌時，不代表需要棄牌。'
    return {'key':key,'level':level,'advice':advice,'source':SOURCE,'entry_chart':chart_entry(cards),
        'published_reference':optional_reference(cards),
        'context':'目前尚未確認行動位置、是否有人加注與大盲倍數，這是條件式參考，不是本手必須下注的指令。'}
