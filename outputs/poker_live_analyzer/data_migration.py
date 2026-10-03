"""保留原檔，驗證完整後才將舊版資料移入使用者目錄。"""
import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4
from control_settings import validate

def migrate_legacy(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        return []
    if not source.is_dir():
        raise ValueError('找不到舊版程式資料夾')
    legacy = source / 'data' if (source / 'data').is_dir() else source
    marker = destination / 'migration.json'
    if marker.exists():
        try:
            if json.loads(marker.read_text(encoding='utf-8')).get('source') == str(source):
                return []
        except (OSError, ValueError):
            pass
    destination.mkdir(parents=True, exist_ok=True)
    stage = destination / 'backups' / ('migration-' + uuid4().hex)
    stage.mkdir(parents=True)
    planned = []
    try:
        settings = legacy / 'control_settings.json'
        if settings.is_file() and not (destination / settings.name).exists():
            content = settings.read_text(encoding='utf-8')
            validate(json.loads(content))
            (stage / settings.name).write_text(content, encoding='utf-8')
            planned.append(Path(settings.name))
        database = legacy / 'history.sqlite3'
        target_database = destination / database.name
        empty_database = False
        if target_database.is_file():
            with closing(sqlite3.connect(target_database.as_uri() + '?mode=ro', uri=True)) as current:
                tables = {row[0] for row in current.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                empty_database = tables <= {'events', 'analyses'} and all(
                    current.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] == 0 for table in tables)
        if database.is_file() and (not target_database.exists() or empty_database):
            with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as old:
                with closing(sqlite3.connect(stage / database.name)) as new:
                    old.backup(new)
                    if new.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise ValueError('舊版歷史資料驗證失敗')
            planned.append(Path(database.name))
        profile_source = source / 'profiles'
        for profile in profile_source.glob('*.json'):
            if profile.is_symlink():
                continue
            relative = Path('profiles') / profile.name
            if (destination / relative).exists():
                continue
            json.loads(profile.read_text(encoding='utf-8'))
            (stage / 'profiles').mkdir(exist_ok=True)
            shutil.copy2(profile, stage / relative)
            planned.append(relative)
        # 原始資料与驗證後副本均保留，既有目的資料永不覆寫。
        for relative in planned:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.name == 'history.sqlite3' and empty_database:
                shutil.copy2(target, stage / '原本空白歷史.sqlite3')
                temporary_database = target.with_suffix('.migration')
                shutil.copy2(stage / relative, temporary_database)
                temporary_database.replace(target)
            elif not target.exists():
                shutil.copy2(stage / relative, target)
        temporary = marker.with_suffix('.tmp')
        temporary.write_text(json.dumps({'source': str(source), 'files': [str(p) for p in planned]}, ensure_ascii=False), encoding='utf-8')
        temporary.replace(marker)
        return planned
    except Exception:
        # 失敗時保留備份及原始資料；下次可重試，沒有成功標記。
        raise
