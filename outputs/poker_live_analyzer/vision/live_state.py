"""把同一幀已確認的可見資料轉成牌局狀態；缺資料就拒絕更新。"""
from uuid import uuid4
from state.models import PokerTableState
from poker.preflop import PositionTracker


class LiveStateAssembler:
    def __init__(self):
        self.hand_id = ''
        self.previous_cards = None
        self.previous_board = ()
        self.waiting_seen = True
        self.position_tracker = PositionTracker()
        self.position_context = {}
        self.blinds = None

    def waiting(self):
        self.waiting_seen = True
        self.position_tracker.reset()
        self.position_context = {}

    def observe_position(self, cards, players, amounts, dealer, blinds, empty_seats=()):
        """位置不等待跟注金額與模擬；只有完整在座證據才鎖定當手名單。"""
        if not cards.reliable or len(cards.hero) != 2 or not players.reliable or getattr(amounts, 'paused', False):
            self.position_context = {}
            return {}
        fields = getattr(amounts, 'field_reliable', {})
        stacks = {s: v for s,v in getattr(amounts, 'seat_stacks', {}).items()
            if fields.get(f'stack_{s}', False)}
        bets = {s: v for s,v in amounts.seat_bets.items() if fields.get(f'bet_{s}', False)}
        occupied = set(players.active_seats) | {0}
        occupied.update(s for s,v in stacks.items() if v > 0)
        occupied.update(s for s,v in bets.items() if v > 0)
        occupied.update(getattr(amounts, 'all_in_seats', ()))
        seats = set(getattr(amounts, 'seats', range(8)))
        complete = seats <= occupied | (set(empty_seats) - occupied)
        context = self.position_tracker.observe(cards.hero, cards.board, occupied, dealer, complete)
        self.blinds = blinds
        big = blinds[1] if blinds else None
        context.update(format='MTT', hero_cards=list(cards.hero), community_cards=list(cards.board),
            stack_bb=None, ante_bb=None, ante_type=None, payout_model=None,
            scenario=None, open_bb=None, opponent_position=None)
        if big and fields.get('hero_stack', False) and all(s in stacks and s in bets for s in occupied - {0}) and 0 in bets:
            hero_total = amounts.hero_stack + bets[0]
            other_totals = [stacks[s] + bets[s] for s in occupied - {0}]
            if other_totals:
                context['stack_bb'] = min(hero_total, max(other_totals)) / big
        mapping = context['positions']
        if big and mapping and set(mapping) <= set(bets) and not cards.board:
            raised = [s for s in mapping if bets[s] > big + .01]
            limpers = [s for s in mapping if s != 0 and bets[s] >= big-.01 and mapping[s] not in ('BB', 'SB', 'BTN/SB')]
            if not raised:
                context['scenario'] = 'vs_limp' if limpers else 'bb_option' if mapping.get(0) == 'BB' else 'open'
            elif len(raised) == 1 and raised[0] != 0 and bets[0] <= big + .01:
                context.update(scenario='vs_open', opponent_position=mapping[raised[0]], open_bb=bets[raised[0]]/big)
        context['reason'] = '位置確認中：莊家或在座人數尚未完整' if not mapping else '沒有條件相符且來源已核實的錦標賽範圍'
        self.position_context = context
        return context

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
        if self.position_context.get('hero_cards') != list(cards.hero):
            self.position_context = {}
        known_effective = all(s in stacks for s in active)
        effective = min(amounts.hero_stack, max(stacks[s] for s in players.active_seats)) if known_effective else 0
        state = PokerTableState(hero_cards=list(cards.hero), community_cards=list(cards.board),
            hero_seat=0, pot=amounts.pot, call_amount=amounts.call_amount,
            hero_stack=amounts.hero_stack, effective_stack=effective,
            dealer_seat=self.position_context.get('dealer_seat'),
            small_blind=self.blinds[0] if self.blinds else 0,
            big_blind=self.blinds[1] if self.blinds else 0,
            decision_context={'preflop': self.position_context},
            hero_turn=getattr(amounts,'hero_turn',None),
            players=[{'seat': s, 'stack': stacks.get(s, 0), 'stack_known': s in stacks, 'current_bet': bets.get(s,0),'bet_known':s in bets,
                'active': s in active, 'folded': s not in active,
                'all_in': s in getattr(amounts,'all_in_seats',()) and s in stacks,
                'name': f'座位{s}', 'position': self.position_context.get('positions', {}).get(s, '')} for s in seats],
            ranges={str(s): 'standard' for s in players.active_seats},
            source='自動畫面', hand_id=hand_id)
        self.hand_id, self.previous_cards, self.previous_board = hand_id, cards.hero, cards.board
        self.waiting_seen = False
        return state.to_dict()
