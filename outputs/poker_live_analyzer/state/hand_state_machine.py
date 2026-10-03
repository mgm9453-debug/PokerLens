"""牌局街次控制；手動修正及新牌局允許明確重置。"""
STREETS=('等待','翻牌前','翻牌','轉牌','河牌','攤牌','完成')

class HandStateMachine:
    @staticmethod
    def validate(previous,current,reset=False):
        if previous is None or reset or current.source in ('手動','manual'):
            return
        if current.hand_id != previous.hand_id and current.hand_id:
            return
        if previous.street=='完成' and current.street=='等待': return
        before=STREETS.index(previous.street)
        after=STREETS.index(current.street)
        if after not in (before,before+1):
            raise ValueError('同一牌局街次不可倒退或跳過；請手動修正、明確重置或提供新牌局編號')
