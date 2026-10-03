from database.repository import StateRepository

class StateHistory:
    def __init__(self,repository): self.repository=repository
    def record(self,event,analysis=None):
        self.repository.save_event(event)
        if analysis is not None: self.repository.save_analysis(event.version,analysis)
    def replay(self): return self.repository.list_events()
