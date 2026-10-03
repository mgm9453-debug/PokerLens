import json
import sqlite3
from state.state_detector import StateEvent

class StateRepository:
    def __init__(self,path):
        self.connection=sqlite3.connect(str(path))
        self.connection.execute('CREATE TABLE IF NOT EXISTS events (version INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
        self.connection.execute('CREATE TABLE IF NOT EXISTS analyses (version INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
        self.connection.commit()
    def save_event(self,event):
        with self.connection: self.connection.execute('INSERT OR REPLACE INTO events VALUES (?,?)',(event.version,json.dumps(event.to_dict(),ensure_ascii=False)))
    def save_analysis(self,version,result):
        data=result.to_dict() if hasattr(result,'to_dict') else result
        with self.connection: self.connection.execute('INSERT OR REPLACE INTO analyses VALUES (?,?)',(version,json.dumps(data,ensure_ascii=False,allow_nan=False)))
    def list_events(self):
        return [StateEvent.from_dict(json.loads(row[0])).to_dict() for row in self.connection.execute('SELECT payload FROM events ORDER BY version')]
    def get_analysis(self,version):
        row=self.connection.execute('SELECT payload FROM analyses WHERE version=?',(version,)).fetchone()
        return json.loads(row[0]) if row else None
    def close(self): self.connection.close()
