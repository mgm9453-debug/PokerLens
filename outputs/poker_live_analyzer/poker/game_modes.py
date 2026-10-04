"""賽制評估與資料限制；不把籌碼與現金賞金混為同一單位。"""
from .pot_odds import call_ev

MODE_LABELS={'cash':'現金局','tournament':'一般錦標賽','mystery':'神秘寶箱'}
MODE_KEYS=('game_mode','rake_known','rake_percent','rake_cap',
    'bounty_active','bounty_known','bounty_average')


def assess_mode(state,equity,win_probability,options):
    mode=options['game_mode']
    result={'mode':mode,'label':MODE_LABELS[mode],'adjusted_call_ev':None,
        'bounty_ev':None,'covered_seats':[],'covering_seats':[],
        'chip_call_ev':call_ev(equity,state.pot,state.call_amount)}
    if mode=='cash':
        result['notice']='抽水尚未確認；目前只顯示未扣抽水的成本估算'
        if options['rake_known']:
            # 前提為此底池適用抽水；不自動推定未翻牌免抽水規則。
            total=state.pot+state.call_amount
            rake=total*options['rake_percent']/100
            if options['rake_cap']>0: rake=min(rake,options['rake_cap'])
            result.update(rake=rake,adjusted_call_ev=equity*(total-rake)-state.call_amount)
            result['notice']='已按設定扣抽水；假設此底池適用抽水、沒有後續下注'
        return result
    result['notice']='尚未計入獎金跳級與出局壓力；籌碼估算不代表完整進場決策'
    if mode=='tournament': return result
    players=[p for p in state.players if p.active and not p.folded and p.seat!=state.hero_seat]
    hero=next((p for p in state.players if p.seat==state.hero_seat),None)
    if hero and hero.stack_known:
        own=hero.stack+hero.total_invested
        result['covered_seats']=[p.seat for p in players if p.stack_known and own>=p.stack+p.total_invested]
        result['covering_seats']=[p.seat for p in players if p.stack_known and own<p.stack+p.total_invested]
    prefix='賞金尚未啟動，沒有當手寶箱收益'
    if options['bounty_active']:
        prefix='賞金已啟動；平均寶箱金額尚未確認'
        if options['bounty_known']:
            prefix=f'平均寶箱 {options["bounty_average"]:,.0f}（賞金貨幣）'
            # 僅已知投入完整、單挑、對手已全下且自身可完全跟注。
            if len(players)==1 and hero and hero.stack_known:
                target=players[0]
                matched=abs(hero.total_invested+state.call_amount-target.total_invested)<1e-6
                if (target.stack_known and target.all_in and target.stack==0 and matched
                        and state.call_amount<=hero.stack and target.seat in result['covered_seats']):
                    result['bounty_ev']=win_probability*options['bounty_average']
                    prefix+=f'｜當手賞金期望 {result["bounty_ev"]:,.1f}（非總收益）'
                else: prefix+='｜淘汰條件未完整確認，未估算賞金收益'
            else: prefix+='｜多人或籌碼不完整，未估算賞金收益'
    result['notice']=prefix+'；'+result['notice']
    return result
