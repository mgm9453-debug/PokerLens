import math

def nonnegative(value, name='金額'):
    if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or value < 0:
        raise ValueError(name + '須為有限非負數')
    return value

def probability(value):
    nonnegative(value, '機率')
    if value > 1: raise ValueError('機率不可大於一')
    return value

def required_equity(pot, call):
    nonnegative(pot); nonnegative(call)
    return call/(pot+call) if pot+call else 0.0

def call_ev(equity, pot, call):
    probability(equity); nonnegative(pot); nonnegative(call)
    return equity*(pot+call)-call

def call_ev_near_boundary(ev, pot, call, samples=0):
    """以相對分池成本和保守抽樣緩衝判斷邊界，不依賴籌碼單位。

    此緩衝不是對手範圍誤差或完整策略收益的信賴區間。
    """
    if ev is None:return True
    nonnegative(pot);nonnegative(call)
    if isinstance(ev,bool) or not isinstance(ev,(int,float)) or not math.isfinite(ev):
        raise ValueError('期望值須為有限數值')
    scale=pot+call
    if not scale:return True
    tolerance=.005
    if type(samples) is int and samples>0:
        tolerance=max(tolerance,1/math.sqrt(samples))
    return abs(ev)/scale<=tolerance

def spr(stack, pot):
    nonnegative(stack); nonnegative(pot)
    return stack/pot if pot else None
