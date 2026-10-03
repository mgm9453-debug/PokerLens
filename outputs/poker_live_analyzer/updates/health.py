import json
import os
from pathlib import Path
from .storage import atomic_json


def report_healthy():
    path = os.environ.get('POKERLENS_HEALTH_PATH')
    token = os.environ.get('POKERLENS_HEALTH_TOKEN')
    if path and token:
        atomic_json(path, {'token':token, 'pid':os.getpid()})


def is_healthy(path, token, pid):
    try:
        with Path(path).open('rb') as stream:
            content = stream.read(4097)
        if len(content) > 4096:
            return False
        value = json.loads(content)
        return isinstance(value, dict) and value.get('token') == token and value.get('pid') == pid
    except (OSError, ValueError, TypeError):
        return False
