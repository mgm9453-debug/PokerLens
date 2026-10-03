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

def spr(stack, pot):
    nonnegative(stack); nonnegative(pot)
    return stack/pot if pot else None
