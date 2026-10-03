from dataclasses import dataclass
from copy import deepcopy
import time
from .models import PokerTableState, validate_confidence
from .hand_state_machine import HandStateMachine

@dataclass
class StateEvent:
    version: int
    state: PokerTableState
    changed_fields: list[str]
    previous_state: dict | None = None
    @property
    def timestamp(self): return self.state.timestamp
    @property
    def current_state(self): return self.state.to_dict()
    def to_dict(self): return {'version':self.version,'state':self.state.to_dict(),'current_state':self.current_state,'previous_state':self.previous_state,'timestamp':self.timestamp,'changed_fields':self.changed_fields}
    @classmethod
    def from_dict(cls,data): return cls(data['version'],PokerTableState.from_dict(data.get('current_state',data.get('state'))),data['changed_fields'],data.get('previous_state'))

class StateDetector:
    def __init__(self):
        self.state=None
        self.version=0
        self.last_error=''
    def update(self,state,confidence=None,reset=False):
        try:
            candidate=PokerTableState.from_dict(state.to_dict() if isinstance(state,PokerTableState) else state)
            supplied={**candidate.confidence,**(confidence or {})}
            validate_confidence(supplied)
            if any(v<.85 for v in supplied.values()) or any(v<.85 for p in candidate.players for v in p.confidence.values()):
                raise ValueError('欄位信心低於 0.85，保留既有狀態')
            HandStateMachine.validate(self.state,candidate,reset)
            data=candidate.to_dict()
            old=self.state.to_dict() if self.state else {}
            ignored={'timestamp','confidence'}
            def normalized(value):
                if isinstance(value,dict): return {k:normalized(v) for k,v in value.items() if k not in ignored}
                if isinstance(value,list): return [normalized(v) for v in value]
                return value
            changed=[k for k in data if k not in ignored and normalized(data[k])!=normalized(old.get(k))]
            self.last_error=''
            if not changed: return None
            candidate.timestamp=max(time.time(),(self.state.timestamp+1e-6) if self.state else 0)
            self.version+=1
            self.state=deepcopy(candidate)
            return StateEvent(self.version,deepcopy(candidate),changed,old or None)
        except (ValueError,TypeError,KeyError) as exc:
            self.last_error=str(exc)
            return None
