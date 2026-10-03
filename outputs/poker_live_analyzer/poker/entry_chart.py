"""使用者提供的起手牌顏色表；顏色是進場規則，不是數字期望值。"""
from .cards import RANKS, validate_cards

ORDER='AKQJT98765432'
# 每列由左至右對應上方點數；忠實保存圖片顏色，不自行改牌格。
ROWS=(
    'BBBBBBBBBBBBB',
    'BBBBBBBBBBBYY',
    'BBBBBBYYYYYYY',
    'BBBBBBYYYYYYY',
    'BBBBBBYYYYYYY',
    'GGGGGBYYYYGGG',
    'BGGGGGBYYYGGG',
    'GGGGGGGBYYGGG',
    'GGGGGGGGBYYGG',
    'GGGGGGGGGBYGG',
    'GGGGGGGGGGBYG',
    'GGGGGGGGGGGGY',
    'GGGGGGGGGGGGG',
)

def chart_entry(cards,board=()):
    if board or len(cards)!=2:
        return {}
    validate_cards(cards)
    first,second=sorted(cards,key=lambda card:RANKS.index(card[0]),reverse=True)
    high,low=ORDER.index(first[0]),ORDER.index(second[0])
    row,column=(high,low) if first[1]==second[1] or high==low else (low,high)
    color={'B':'藍色','Y':'黃色','G':'灰色'}[ROWS[row][column]]
    return {'color':color,'rule':{'藍色':'可考慮進場','黃色':'看位置與下注','灰色':'不主動進場'}[color],
        'source':'使用者指定起手牌表','numeric_ev':None}
