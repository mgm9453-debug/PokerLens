"""把同一幀已確認的可見資料轉成牌局狀態；缺資料就拒絕更新。"""
from uuid import uuid4
from state.models import PokerTableState


class LiveStateAssembler:
    def __init__(self):
        self.hand_id = ''
        self.previous_cards = None
        self.previous_board = ()
        self.waiting_seen = True

    def waiting(self):
        self.waiting_seen = True

    def build(self, cards, players, amounts):
        if not cards.reliable or cards.confidence < .85 or len(cards.hero) != 2:
            raise ValueError('底牌尚未確認')
        if not players.reliable or not players.active_seats:
            raise ValueError(players.reason or '尚無可靠持牌對手資料')
        partial=bool(getattr(amounts,'core_reliable',False))
        if not amounts.reliable and not partial:
            raise ValueError(amounts.reason or '金額尚未確認')
        fields = getattr(amounts, 'field_reliable', {})
        if partial and any(getattr(amounts,key,None) is None or not fields.get(key,False)
                for key in ('pot','hero_stack','call_amount')):
            raise ValueError('跟注所需的底池、自身籌碼或跟注額尚未確認')
        seats=getattr(amounts,'seats',tuple(range(8)))
        if not set(players.active_seats).issubset(seats) or 0 not in seats:
            raise ValueError('持牌座位與牌桌版型不一致')
        if not partial and set(amounts.seat_bets) != set(seats):
            raise ValueError('各座位下注尚未全部確認')
        bets={seat:value for seat,value in amounts.seat_bets.items()
            if seat in seats and (not partial or fields.get(f'bet_{seat}',False))}
        if set(players.active_seats)|{0} <= set(bets):
            highest = max(bets[s] for s in players.active_seats)
            expected = min(amounts.hero_stack, max(0, highest-bets[0]))
            if abs(expected-amounts.call_amount) > .01:
                raise ValueError(f'跟注金額不一致：按鈕 {amounts.call_amount:,.0f}、計算差額 {expected:,.0f}（最高下注 {highest:,.0f}、自己已下 {bets[0]:,.0f}）')
        new_hand = self.waiting_seen or self.previous_cards != cards.hero or (self.previous_board and not cards.board)
        hand_id = uuid4().hex if new_hand else self.hand_id
        stacks = {s: value for s, value in getattr(amounts, 'seat_stacks', {}).items()
            if fields.get(f'stack_{s}', False)}
        stacks[0] = amounts.hero_stack
        active = set(players.active_seats) | {0}
        known_effective = all(s in stacks for s in active)
        effective = min(amounts.hero_stack, max(stacks[s] for s in players.active_seats)) if known_effective else 0
        state = PokerTableState(hero_cards=list(cards.hero), community_cards=list(cards.board),
            hero_seat=0, pot=amounts.pot, call_amount=amounts.call_amount,
            hero_stack=amounts.hero_stack, effective_stack=effective,
            hero_turn=getattr(amounts,'hero_turn',None),
            players=[{'seat': s, 'stack': stacks.get(s, 0), 'stack_known': s in stacks, 'current_bet': bets.get(s,0),'bet_known':s in bets,
                'active': s in active, 'folded': s not in active,
                'all_in': s in getattr(amounts,'all_in_seats',()) and s in stacks,
                'name': f'座位{s}', 'position': '籌碼已確認' if s in stacks else '籌碼未讀取'} for s in seats],
            ranges={str(s): 'standard' for s in players.active_seats},
            source='自動畫面', hand_id=hand_id)
        self.hand_id, self.previous_cards, self.previous_board = hand_id, cards.hero, cards.board
        self.waiting_seen = False
        return state.to_dict()
