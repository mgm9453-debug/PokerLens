"""以隔離資料與健康訊號驗證已打包程式，僅關閉本次建立的視窗。"""
import argparse
import ctypes
import json
import os
import subprocess
import time
from pathlib import Path
from ctypes import wintypes


def close_windows(pid):
    user32 = ctypes.windll.user32
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    windows = []

    def visit(window, unused):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
        if owner.value == pid:
            windows.append(window)
        return True

    user32.EnumWindows(callback(visit), 0)
    for window in windows:
        user32.PostMessageW(window, 0x0010, 0, 0)
    return len(windows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--launcher', action='store_true')
    args = parser.parse_args()
    root, data = args.root.resolve(), args.data.resolve()
    data.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment['PATH'] = os.pathsep.join([str(Path(os.environ['SystemRoot']) / 'System32'), os.environ['SystemRoot']])
    environment['POKERLENS_DATA_DIR'] = str(data)
    if args.launcher:
        health_dir = data / 'health'
        health_dir.mkdir(exist_ok=True)
        previous = set(health_dir.glob('*.json'))
        command = [str(root / 'Launcher.exe'), '--root', str(root), '--data', str(data)]
    else:
        state = json.loads((root / 'current.json').read_text())
        environment['POKERLENS_HEALTH_PATH'] = str(data / 'manual-health.json')
        environment['POKERLENS_HEALTH_TOKEN'] = '0123456789abcdef0123456789abcdef'
        command = [str(root / 'versions' / state['version'] / 'PokerLens.exe'), '--manual']
        Path(environment['POKERLENS_HEALTH_PATH']).unlink(missing_ok=True)
    process = subprocess.Popen(command, env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
    if args.launcher and environment.get('POKERLENS_VERIFY_RELEASE') == '1':
        result = process.wait(timeout=60)
        report_path = data / '發布驗證.json'
        if result != 0 or not report_path.exists():
            raise SystemExit('啟動器黑箱驗證失敗')
        report = json.loads(report_path.read_text(encoding='utf-8'))
        if not all(report.get(name) for name in ('fonts', 'models', 'ocr_runtime', 'capture_runtime')):
            raise SystemExit('正式版本缺少必要資源')
        evidence = {'launcher': True, 'healthy': True, 'exit_code': result, 'python_removed_from_path': True, 'resource_report': report}
        (data / '打包驗證.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(evidence, ensure_ascii=False))
        return
    deadline = time.monotonic() + 40
    health = None
    while time.monotonic() < deadline and process.poll() is None:
        candidates = list(set(health_dir.glob('*.json')) - previous) if args.launcher else [Path(environment['POKERLENS_HEALTH_PATH'])]
        for candidate in candidates:
            if candidate.exists():
                try:
                    health = json.loads(candidate.read_text())
                except (ValueError, OSError):
                    continue
        if health:
            break
        time.sleep(.2)
    if not health:
        close_windows(process.pid)
        raise SystemExit('已打包程式未產生健康訊號')
    time.sleep(2)
    count = close_windows(health['pid'])
    result = process.wait(timeout=20)
    evidence = {'launcher': args.launcher, 'pid': health['pid'], 'healthy': True, 'closed_windows': count, 'exit_code': result, 'python_removed_from_path': True}
    (data / '打包驗證.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(evidence, ensure_ascii=False))
    if result != 0 or (count == 0 and environment.get('POKERLENS_VERIFY_RELEASE') != '1'):
        raise SystemExit('已打包程式未正常結束')


if __name__ == '__main__':
    main()
