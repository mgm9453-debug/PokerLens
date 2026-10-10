"""行動、矩陣與浮窗共用配色，不改變決策。"""
from PySide6.QtGui import QColor

ROLE_KEYS={'call_color':'preflop_call','fold_color':'preflop_fold','check_color':'preflop_check','raise_color':'preflop_raise'}

def action_color(role,options):
    from control_settings import DEFAULTS
    key=ROLE_KEYS.get(role)
    return options.get(key,DEFAULTS[key]) if key else '#ffffff'

def readable_color(color):
    """深色動作使用可讀的同色系文字；所有區塊使用相同轉換。"""
    source=QColor(color)
    if max(source.red(),source.green(),source.blue())<110:
        return QColor(*(round(channel*.45+255*.55) for channel in (source.red(),source.green(),source.blue()))).name()
    return source.name()
