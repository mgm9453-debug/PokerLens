from __future__ import annotations
import contextlib
import ctypes
import json
import os
import time
import uuid
from pathlib import Path
from .security import UpdateError, parse_version


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_state(root):
    try:
        state = json.loads((Path(root)/'current.json').read_text(encoding='utf-8-sig'))
        parse_version(state['version'])
        if state.get('previous') is not None:
            parse_version(state['previous'])
        if type(state.get('pending', False)) is not bool:
            raise ValueError()
        return state
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise UpdateError('目前版本指標無效') from exc


def rollback(root):
    state = load_state(root)
    previous = state.get('previous')
    if not previous:
        raise UpdateError('沒有可回復的舊版本')
    atomic_json(Path(root)/'current.json', {'version':previous, 'previous':None, 'pending':False})
    return previous


@contextlib.contextmanager
def installation_lock(root, timeout=0):
    lock = Path(root)/'.update.lock'
    Path(root).mkdir(parents=True, exist_ok=True)
    stream = lock.open('a+b')
    try:
        deadline = time.monotonic() + timeout
        if os.name == 'nt':
            import msvcrt
            stream.seek(0)
            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b'0')
                stream.flush()
            stream.seek(0)
            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise UpdateError('另一個啟動或更新程序正在處理') from exc
                    time.sleep(0.1)
        else:
            import fcntl
            while True:
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise UpdateError('另一個啟動或更新程序正在處理') from exc
                    time.sleep(0.1)
        yield
    finally:
        stream.close()


def wait_for_exit(pid, timeout=60):
    if pid is None:
        return
    if type(pid) is not int or pid <= 0 or pid == os.getpid():
        raise UpdateError('等待程序識別碼無效')
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x100000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return
            raise UpdateError('無法確認舊程序是否已結束')
        try:
            kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            result = kernel.WaitForSingleObject(handle, int(timeout * 1000))
            if result != 0:
                raise UpdateError('舊程序仍在執行，更新未切換')
        finally:
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle(handle)
    else:
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.1)
        raise UpdateError('舊程序仍在執行，更新未切換')
