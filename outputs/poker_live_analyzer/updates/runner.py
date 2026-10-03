from __future__ import annotations
import ctypes
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from .health import is_healthy
from .security import UpdateError
from .storage import atomic_json, installation_lock, load_state, rollback


def configure_logging(user_data):
    logs = Path(user_data)/'logs'
    logs.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=logs/'updates.log', level=logging.INFO, encoding='utf-8', format='%(asctime)s %(levelname)s %(message)s')


def show_error(message):
    logging.error(message)
    if os.name == 'nt':
        ctypes.windll.user32.MessageBoxW(None, str(message), 'PokerLens 啟動與更新', 0x10)


def update_display_version(version):
    if os.name != 'nt':
        return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Uninstall\PokerLens_is1', 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, 'DisplayVersion', 0, winreg.REG_SZ, version)
    except OSError:
        logging.warning('未找到使用者安裝記錄，略過版本顯示更新')


def launch(root, user_data, health_timeout=30, process_factory=subprocess.Popen):
    root, user_data = Path(root), Path(user_data)
    configure_logging(user_data)
    with installation_lock(root):
        state = load_state(root)
        try:
            process, healthy = _start(root, user_data, state, health_timeout, process_factory)
        except UpdateError:
            if not state.get('pending') or not state.get('previous'):
                raise
            rollback(root)
            state = load_state(root)
            process, healthy = _start(root, user_data, state, health_timeout, process_factory)
        if not healthy:
            if state.get('pending') and state.get('previous'):
                previous = rollback(root)
                logging.error('新版健康檢查失敗，已回復版本 %s', previous)
                if process.poll() is None:
                    raise UpdateError('新版尚未結束，已回復舊版本指標；請關閉目前程式後重新啟動')
                process, healthy = _start(root, user_data, load_state(root), health_timeout, process_factory)
            if not healthy:
                raise UpdateError('程式健康檢查失敗，未強制結束程序')
        state = load_state(root)
        was_update = state.get('pending', False)
        if was_update:
            state['pending'] = False
            atomic_json(root/'current.json', state)
            update_display_version(state['version'])
            logging.info('新版已通過健康檢查')
        # 健康確認後留在監護程序，偵測新版第一次執行的異常退出。
        result = process.wait()
        if result != 0 and was_update and state.get('previous'):
            rollback(root)
            update_display_version(state['previous'])
            logging.error('新版異常退出，已回復舊版本')
            old_process, old_healthy = _start(root, user_data, load_state(root), health_timeout, process_factory)
            if not old_healthy:
                raise UpdateError('回復的舊版本未通過健康檢查')
            return old_process.wait()
        return result


def _start(root, user_data, state, timeout, process_factory):
    version_dir = root/'versions'/state['version']
    executable = version_dir/'PokerLens.exe'
    if not executable.is_file() or not version_dir.resolve().is_relative_to((root/'versions').resolve()):
        raise UpdateError('目前版本主程式不存在或路徑不安全')
    health_dir = user_data/'health'
    health_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    health_path = health_dir/(token + '.json')
    environment = os.environ.copy()
    environment.update({'POKERLENS_HEALTH_PATH':str(health_path), 'POKERLENS_HEALTH_TOKEN':token, 'POKERLENS_DATA_DIR':str(user_data)})
    try:
        process = process_factory([str(executable)], cwd=version_dir, env=environment)
    except OSError as exc:
        raise UpdateError('無法啟動目前版本，已保留舊版') from exc
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if is_healthy(health_path, token, process.pid):
                return process, True
            if process.poll() is not None:
                return process, False
            time.sleep(0.1)
        return process, False
    finally:
        health_path.unlink(missing_ok=True)
