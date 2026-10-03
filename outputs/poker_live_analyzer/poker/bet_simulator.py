from dataclasses import dataclass
from .pot_odds import nonnegative, probability, required_equity, spr

@dataclass(frozen=True)
class BetScenario:
    percentage: int
    bet: float
    new_pot: float
    required_equity: float
    spr: float | None
    ev: float

def simulate_bets(pot, effective_stack, equity, fold_probability=0.0,percentages=(25,33,50,66,75,100,125)):
    nonnegative(pot); nonnegative(effective_stack); probability(equity); probability(fold_probability)
    rows = []
    for percentage in percentages:
        if type(percentage) is not int or not 0<percentage<=200: raise ValueError('下注比例須為正整數且不超過百分之二百')
        bet = min(pot*percentage/100, effective_stack)
        new_pot = pot+2*bet
        ev = fold_probability*pot+(1-fold_probability)*(equity*new_pot-bet)
        rows.append(BetScenario(percentage,bet,new_pot,required_equity(pot+bet,bet),spr(effective_stack-bet,new_pot),ev))
    return rows
