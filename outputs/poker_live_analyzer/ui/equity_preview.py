"""牌面與對手已確認時，獨立估算勝率，不依賴金額。"""
from threading import Event
from PySide6.QtCore import QThread,Signal
from poker.equity import calculate_equity
from poker.evaluator import evaluate_hand


class EquityPreviewWorker(QThread):
    succeeded=Signal(object,object)
    failed=Signal(object,str)

    def __init__(self,key,observation,range_name,parent=None):
        super().__init__(parent)
        self.key=key
        self.observation=observation
        self.range_name=range_name
        self.cancel=Event()

    def run(self):
        try:
            hero=self.observation['hero']
            board=self.observation['board']
            equity=calculate_equity(hero,board,[self.range_name]*len(self.observation['active_seats']),
                iterations=2000,cancel=self.cancel.is_set)
            if equity.cancelled or self.cancel.is_set(): return
            self.succeeded.emit(self.key,{'equity_only':True,'live':True,'hero_cards':hero,
                'community_cards':board,'equity':equity.hero_equity,'opponent_equity':equity.opponents_equity,
                'tie_probability':equity.tie_probability,'equity_details':equity.to_dict(),
                'hand_strength':evaluate_hand(hero,board).category,'simulation_count':equity.iterations_completed,
                'spr':None,'opponents':len(self.observation['active_seats'])})
        except Exception as error:
            if not self.cancel.is_set(): self.failed.emit(self.key,str(error))
