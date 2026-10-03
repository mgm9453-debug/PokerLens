import json
import sqlite3
from pathlib import Path
import pytest
from app_paths import user_data_dir, resource_path
from data_migration import migrate_legacy
from version import CURRENT_VERSION, PRODUCT_PATH

def test_single_version_source():
    assert CURRENT_VERSION == json.loads(PRODUCT_PATH.read_text(encoding='utf-8'))['version']

def test_data_is_separate(monkeypatch, tmp_path):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.delenv('POKERLENS_DATA_DIR', raising=False)
    assert user_data_dir() == tmp_path / 'PokerLens'
    assert resource_path('models').is_dir()

def test_migration_preserves_original_and_existing(tmp_path):
    old, target = tmp_path / 'old', tmp_path / 'user'
    (old / 'data').mkdir(parents=True)
    (old / 'data' / 'control_settings.json').write_text('{"iterations":10000}', encoding='utf-8')
    with sqlite3.connect(old / 'data' / 'history.sqlite3') as database:
        database.execute('CREATE TABLE evidence (value TEXT)')
        database.execute("INSERT INTO evidence VALUES ('保留')")
    migrate_legacy(old, target)
    with sqlite3.connect(target / 'history.sqlite3') as database:
        assert database.execute('SELECT value FROM evidence').fetchone() == ('保留',)
    assert (old / 'data' / 'history.sqlite3').exists()
    assert migrate_legacy(old, target) == []

def test_invalid_settings_do_not_mark_success(tmp_path):
    old = tmp_path / 'old'
    old.mkdir()
    (old / 'control_settings.json').write_text('{"iterations":3}', encoding='utf-8')
    with pytest.raises(ValueError):
        migrate_legacy(old, tmp_path / 'new')
    assert not (tmp_path / 'new' / 'migration.json').exists()

def test_migration_does_not_override(tmp_path):
    old, target = tmp_path / 'old', tmp_path / 'new'
    old.mkdir(); target.mkdir()
    (old / 'control_settings.json').write_text('{"iterations":10000}', encoding='utf-8')
    (target / 'control_settings.json').write_text('{"iterations":50000}', encoding='utf-8')
    migrate_legacy(old, target)
    assert json.loads((target / 'control_settings.json').read_text())['iterations'] == 50000

def test_empty_first_start_database_can_import(tmp_path):
    old, target = tmp_path / 'old', tmp_path / 'new'
    old.mkdir(); target.mkdir()
    for directory in (old, target):
        with sqlite3.connect(directory / 'history.sqlite3') as database:
            database.execute('CREATE TABLE events (version INTEGER PRIMARY KEY, payload TEXT)')
        database.close()
    with sqlite3.connect(old / 'history.sqlite3') as database:
        database.execute("INSERT INTO events VALUES (1, '歷史')")
    assert Path('history.sqlite3') in migrate_legacy(old, target)
    with sqlite3.connect(target / 'history.sqlite3') as database:
        assert database.execute('SELECT payload FROM events').fetchone() == ('歷史',)

def test_nonempty_database_is_preserved(tmp_path):
    old, target = tmp_path / 'old', tmp_path / 'new'
    old.mkdir(); target.mkdir()
    for directory in (old, target):
        with sqlite3.connect(directory / 'history.sqlite3') as database:
            database.execute('CREATE TABLE events (version INTEGER PRIMARY KEY, payload TEXT)')
            database.execute('INSERT INTO events VALUES (1, ?)', (directory.name,))
    migrate_legacy(old, target)
    with sqlite3.connect(target / 'history.sqlite3') as database:
        assert database.execute('SELECT payload FROM events').fetchone() == ('new',)
