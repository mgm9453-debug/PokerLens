from poker.starting_hands import starting_hand_guide
from poker.evaluator import evaluate_hand
from tests.test_threats import make_state
from poker.threats import calculate_threats

def test_premium_does_not_mean_always_call_large_raise():
    for cards in (['As','Ad'],['Ks','Kd'],['Qs','Qd'],['Js','Jd'],['Ah','Kh'],['Ac','Qc']):
        guide=starting_hand_guide(cards)
        assert guide['level']=='強起手牌'
        assert '前面沒有人加注' in guide['advice']
        assert '籌碼' in guide['advice']

def test_suited_and_offsuit_aq_differ_and_postflop_hides_guide():
    assert starting_hand_guide(['Ac','Qd'])['level']=='大點數起手牌'
    assert starting_hand_guide(['9h','8h'])['level']=='同花發展型起手牌'
    assert not starting_hand_guide(['As','Ad'],['3h','4h','5s'])

def test_flop_and_turn_pictures_really_beat_hero_without_future_cards():
    for board in (['Ah','7c','2d'],['Ah','7c','2d','Qc']):
        hero=['As','Qd']
        result=calculate_threats(make_state(hero,board,{'1':'AK AA KK QQ 77 22'}))
        assert len(result.visual_examples)==len(result.beating_hand_types)
        for example in result.visual_examples:
            assert len(example['best_five'])==5
            assert set(example['best_five'])<=set(board+example['hole_cards'])
            assert not set(example['hole_cards'])&set(board+hero)
            assert evaluate_hand(example['hole_cards'],board).score<evaluate_hand(hero,board).score
            assert evaluate_hand(example['best_five'],[]).score==evaluate_hand(example['hole_cards'],board).score
