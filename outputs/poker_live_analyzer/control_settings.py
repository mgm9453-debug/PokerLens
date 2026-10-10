"""獨立控制台與分析器共用的設定，透過原子寫入避免半份資料。"""
import json
from pathlib import Path

DEFAULTS={'probability_font':32,'action_font':30,'text_font':20,'refresh_ms':100,
    'iterations':50000,'opponent_range':'standard','bet_percentages':[25,33,50,66,75,100,125],
    'auto_dock':True,'show_chips':True,'show_threats':True,'picture_scale':100,
    'game_mode':'tournament','rake_known':False,'rake_percent':5,'rake_cap':0,
    'bounty_active':False,'bounty_known':False,'bounty_average':0,
    'matrix_background':'#00cc66','matrix_winner':'#ef4444',
    'preflop_background':'#34373b','preflop_raise':'#9d2638','preflop_call':'#087553',
    'preflop_fold':'#182333','preflop_check':'#655124',
    'win_color':'#087d55','tie_color':'#7045b4','call_color':'#087d55',
    'fold_color':'#c42b36','check_color':'#1765aa','wait_color':'#9a6500'}
LIMITS={'probability_font':(24,48),'action_font':(24,44),'text_font':(14,26),'refresh_ms':(100,1000)}
LIMITS['picture_scale']=(75,125)
LIMITS.update(rake_percent=(0,20),rake_cap=(0,1000000),bounty_average=(0,1000000))
from app_paths import user_data_dir
PATH=user_data_dir()/'control_settings.json'

def validate(data):
    if not isinstance(data,dict): raise ValueError('設定須為有效物件')
    result={**DEFAULTS,'bet_percentages':list(DEFAULTS['bet_percentages'])}
    for key,value in data.items():
        if key not in DEFAULTS: raise ValueError('未知設定項目')
        if key in LIMITS:
            low,high=LIMITS[key]
            valid=type(value) is int and low<=value<=high
        elif key=='iterations': valid=type(value) is int and value in (10000,50000,100000)
        elif key=='opponent_range': valid=value in ('tight','standard','loose')
        elif key=='game_mode': valid=value in ('cash','tournament','mystery')
        elif key in ('rake_known','bounty_active','bounty_known'): valid=type(value) is bool
        elif key=='bet_percentages':
            valid=isinstance(value,list) and bool(value) and all(type(v) is int and v in (25,33,50,66,75,100,125,150) for v in value) and len(value)==len(set(value))
        elif key.startswith('show_') or key=='auto_dock': valid=type(value) is bool
        else:
            import re
            valid=isinstance(value,str) and bool(re.fullmatch(r'#[0-9a-fA-F]{6}',value))
        if not valid: raise ValueError('設定超出允許範圍')
        result[key]=list(value) if key=='bet_percentages' else value
    return result

def read(path=PATH):
    path=Path(path)
    return validate(json.loads(path.read_text(encoding='utf-8'))) if path.exists() else validate({})

def write(data,path=PATH):
    path=Path(path)
    result=validate(data)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)

