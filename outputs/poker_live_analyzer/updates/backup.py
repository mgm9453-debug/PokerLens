"""更新切換前保存白名單資料，成功標記後才允許切換。"""
from __future__ import annotations
import hashlib
import logging
import os
import shutil
import sqlite3
import stat
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from .security import UpdateError, parse_version
from .storage import atomic_json


def _is_link(path):
    status = path.lstat()
    return stat.S_ISLNK(status.st_mode) or bool(getattr(status, 'st_file_attributes', 0) & 0x400)


def snapshot_user_data(user_data, from_version, to_version):
    parse_version(from_version)
    parse_version(to_version)
    root = Path(user_data)
    destination = root/'backups'/f'update-{from_version}-to-{to_version}-{uuid.uuid4().hex}'
    copied = []
    try:
        if root.exists() and _is_link(root):
            raise UpdateError('使用者資料根目錄是連結，拒絕備份與切換')
        if (root/'backups').exists() and _is_link(root/'backups'):
            raise UpdateError('備份目錄是連結，拒絕備份與切換')
        destination.mkdir(parents=True)
        database = root/'history.sqlite3'
        if database.exists() or database.is_symlink():
            if _is_link(database) or not database.is_file():
                raise UpdateError('歷史資料庫是連結或無效檔案，拒絕備份與切換')
            deadline = time.monotonic() + 60
            def check_deadline(status, remaining, total):
                if time.monotonic() > deadline:
                    raise UpdateError('歷史資料庫備份逾時，拒絕切換')
            with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True, timeout=5)) as source:
                with closing(sqlite3.connect(destination/'history.sqlite3')) as target:
                    source.backup(target, pages=256, progress=check_deadline, sleep=0.05)
                    if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise UpdateError('歷史資料庫備份完整性驗證失敗')
            copied.append(Path('history.sqlite3'))
        candidates = [root/'control_settings.json']
        for name in ('profiles','ranges'):
            directory = root/name
            if directory.exists() and not _is_link(directory) and directory.is_dir():
                candidates.extend(directory.glob('*.json'))
        for source in candidates:
            if not source.exists() or _is_link(source) or not source.is_file():
                continue
            relative = source.relative_to(root)
            target = destination/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target, follow_symlinks=False)
            if _is_link(target):
                raise UpdateError('備份過程出現資料連結，拒絕切換')
            copied.append(relative)
        entries = []
        for relative in copied:
            path = destination/relative
            digest = hashlib.sha256()
            with path.open('r+b') as stream:
                for block in iter(lambda:stream.read(1024*1024), b''):
                    digest.update(block)
                stream.flush()
                os.fsync(stream.fileno())
            entries.append({'path':relative.as_posix(), 'size':path.stat().st_size, 'sha256':digest.hexdigest()})
        atomic_json(destination/'snapshot.json', {'schema':1, 'from_version':from_version, 'to_version':to_version,
                    'created_at':datetime.now(timezone.utc).isoformat(), 'files':entries, 'automatic_restore':False})
        logging.info('更新前資料備份已完成：%s', destination)
        return destination
    except UpdateError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise UpdateError('更新前資料備份失敗，已保留原始資料與目前版本') from exc
