"""大盲數的顯示與讀取精度；舊資料不擅自改變單位。"""
import math


def format_amount(value, unit='BB', signed=False):
    if value is None: return '待確認'
    if unit != 'BB': return format(value, '+,.0f' if signed else ',.0f')
    return format(value, '+,.4f' if signed else ',.4f').rstrip('0').rstrip('.') + ' BB'


def rounding_budget(unit, resolutions, *keys):
    if unit != 'BB': return .01
    return sum(resolutions.get(key, 0) for key in set(keys)) / 2 + 1e-9


def validate_resolutions(resolutions):
    if not isinstance(resolutions, dict): raise ValueError('金額讀取精度須為字典')
    for key, value in resolutions.items():
        if not isinstance(key, str) or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 2:
            raise ValueError('金額讀取精度須為零至二之間的有限數值')


def state_in_bb(data):
    """只在大盲基準已知時轉換舊牌局，原紀錄保持不變。"""
    from copy import deepcopy
    result=deepcopy(data)
    if result.get('amount_unit')=='BB': return result
    blind=result.get('big_blind',0)
    monetary=('pot','call_amount','hero_stack','effective_stack','small_blind')
    if not isinstance(blind,(int,float)) or isinstance(blind,bool) or not math.isfinite(blind) or blind<=0:
        if any(result.get(key,0) for key in monetary) or any(p.get(key,0) for p in result.get('players',[]) for key in ('stack','bet','current_bet','total_invested')):
            raise ValueError('舊牌局缺少大盲基準，不能換算為大盲數；請建立新的大盲數牌局')
        blind=1
    for key in monetary:
        if key in result: result[key]/=blind
    for player in result.get('players',[]):
        for key in ('stack','bet','current_bet','total_invested'):
            if player.get(key) is not None: player[key]/=blind
    result.update(amount_unit='BB',big_blind=1,amount_resolution={})
    return result
