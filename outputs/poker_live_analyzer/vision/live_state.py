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
        if not amounts.reliable:
            raise ValueError(amounts.reason or '金額尚未確認')
        if set(amounts.seat_bets) != set(range(8)):
            raise ValueError('各座位下注尚未全部確認')
        highest = max(amounts.seat_bets[s] for s in players.active_seats)
        expected = min(amounts.hero_stack, max(0, highest-amounts.seat_bets[0]))
        if abs(expected-amounts.call_amount) > .01:
            raise ValueError(f'跟注金額不一致：按鈕 {amounts.call_amount:,.0f}、計算差額 {expected:,.0f}（最高下注 {highest:,.0f}、自己已下 {amounts.seat_bets[0]:,.0f}）')
        new_hand = self.waiting_seen or self.previous_cards != cards.hero or (self.previous_board and not cards.board)
        hand_id = uuid4().hex if new_hand else self.hand_id
        fields = getattr(amounts, 'field_reliable', {})
        stacks = {s: value for s, value in getattr(amounts, 'seat_stacks', {}).items()
            if fields.get(f'stack_{s}', False)}
        stacks[0] = amounts.hero_stack
        active = set(players.active_seats) | {0}
        known_effective = all(s in stacks for s in active)
        effective = min(amounts.hero_stack, max(stacks[s] for s in players.active_seats)) if known_effective else 0
        state = PokerTableState(hero_cards=list(cards.hero), community_cards=list(cards.board),
            hero_seat=0, pot=amounts.pot, call_amount=amounts.call_amount,
            hero_stack=amounts.hero_stack, effective_stack=effective,
            players=[{'seat': s, 'stack': stacks.get(s, 0), 'stack_known': s in stacks, 'current_bet': amounts.seat_bets[s],
                'active': s in active, 'folded': s not in active,
                'name': f'座位{s}', 'position': '籌碼已確認' if s in stacks else '籌碼未讀取'} for s in range(8)],
            ranges={str(s): 'standard' for s in players.active_seats},
            source='自動畫面', hand_id=hand_id)
        self.hand_id, self.previous_cards, self.previous_board = hand_id, cards.hero, cards.board
        self.waiting_seen = False
        return state.to_dict()
