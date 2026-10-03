import argparse
import logging
import subprocess
from pathlib import Path
from updates.client import UpdateClient
from updates.runner import configure_logging, show_error
from updates.security import UpdateError


def main():
    parser = argparse.ArgumentParser(description='PokerLens 獨立更新程序')
    parser.add_argument('--product', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--wait-pid', type=int)
    args = parser.parse_args()
    configure_logging(args.data)
    try:
        client = UpdateClient(args.product, args.root, args.data)
        release = client.package(args.package)
        client.install(release, args.package, args.wait_pid)
        subprocess.Popen([str(args.root/'Launcher.exe'), '--root', str(args.root), '--data', str(args.data)], cwd=args.root)
        return 0
    except (UpdateError, OSError) as exc:
        try:
            subprocess.Popen([str(args.root/'Launcher.exe'), '--root', str(args.root), '--data', str(args.data)], cwd=args.root)
            logging.info('更新失敗，已重新呼叫目前版本啟動入口')
        except OSError:
            logging.error('目前版本啟動入口亦無法開啟，請手動重新啟動')
        show_error(str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
