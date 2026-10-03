import argparse
import json
import sys
import os
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from app_paths import prepare_data_dir, resource_path, install_root
from version import APP_NAME, CURRENT_VERSION, PRODUCT_PATH


def main():
    parser = argparse.ArgumentParser(description='德州撲克牌局分析與訓練工具')
    parser.add_argument('--smoke-test', action='store_true', help='驗證假資料更新流程後退出')
    parser.add_argument('--auto-detect', action='store_true', help='啟動後追蹤目前牌桌')
    parser.add_argument('--manual', action='store_true', help='使用手動輸入模式')
    parser.add_argument('--settings', action='store_true', help='開啟獨立設定控制台')
    parser.add_argument('--verify-release', action='store_true', help='驗證正式版本資源及啟動後自動結束')
    args = parser.parse_args()
    args.verify_release = args.verify_release or os.environ.get('POKERLENS_VERIFY_RELEASE') == '1'
    app = QApplication(sys.argv[:1])
    app.setStyle('Fusion')
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(CURRENT_VERSION)
    from PySide6.QtGui import QIcon
    app.setWindowIcon(QIcon(str(resource_path('assets/PokerLens.ico'))))
    data_dir = prepare_data_dir() if not args.smoke_test else Path(__file__).parent / 'data' / 'smoke'
    from app_logging import configure_logging
    configure_logging(data_dir)
    guard = None
    if not args.smoke_test and not args.settings:
        from instance_guard import InstanceGuard
        guard = InstanceGuard(data_dir)
        if not guard.acquire():
            return 0
    migration_message = ''
    if not args.smoke_test and not args.settings:
        from data_migration import migrate_legacy
        import logging
        try:
            request = data_dir / 'migration_request.json'
            if request.is_file():
                source = json.loads(request.read_text(encoding='utf-8'))['source']
                imported = migrate_legacy(source, data_dir)
                request.unlink()
                migration_message = f'已匯入 {len(imported)} 項資料。已有內容不會覆寫，舊資料與備份均已保留。'
            elif not getattr(sys, 'frozen', False):
                migrate_legacy(Path(__file__).parent, data_dir)
        except Exception:
            logging.exception('舊版資料匯入失敗，原始資料已保留')
            migration_message = '匯入未完成，原始資料與備份已保留。請在設定內重新選擇舊版資料夾。'
    if args.settings:
        from settings_control import create_window
        settings_window = create_window()
        settings_window.show()
        return app.exec()
    live = not args.smoke_test and not args.manual and not args.verify_release
    window = MainWindow(auto_demo=args.manual and not args.smoke_test,
                        data_dir=data_dir)
    if guard:
        guard.bind(window)
    if not args.smoke_test:
        from ui.update_dialog import UpdateController
        window.update_controller = UpdateController(window, PRODUCT_PATH, install_root() or Path(__file__).parent, data_dir)
        window.update_controller.install_requested.connect(window.install_update)
        window.update_controller.idle.connect(window.resume_pending_close)
        window.update_controller.startup_check()
    if live or args.auto_detect:
        window.set_live_layout()
    window.show()
    if migration_message:
        from PySide6.QtWidgets import QMessageBox
        QTimer.singleShot(0, lambda: QMessageBox.information(window, '資料匯入', migration_message))
    if not args.smoke_test:
        from updates.health import report_healthy
        QTimer.singleShot(1000, report_healthy)
    if args.verify_release:
        from vision.card_classifier import CardClassifier
        from vision.suit_classifier import SuitClassifier
        from ui.fonts import interface_font
        from winrt.windows.media.ocr import OcrEngine
        import windows_capture
        CardClassifier()
        SuitClassifier()
        checks = {'version': CURRENT_VERSION, 'fonts': interface_font().families(),
                  'models': True, 'ocr_runtime': OcrEngine is not None,
                  'capture_runtime': windows_capture is not None, 'data_dir': str(data_dir)}
        (data_dir / '發布驗證.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
        QTimer.singleShot(2500, window.close)
    if live or args.auto_detect:
        QTimer.singleShot(0, window.toggle_auto)
    if args.smoke_test:
        window.settings.iterations.setCurrentIndex(0)
        window.apply_editor()
        initial_version = window.detector.version
        checks = {'first_analysis': False, 'changed_analysis': False, 'unchanged_skipped': False}
        elapsed = [0]
        timer = QTimer()

        def poll():
            elapsed[0] += 100
            if window.result and not checks['first_analysis']:
                checks['first_analysis'] = True
                window.apply_editor()
                checks['unchanged_skipped'] = window.detector.version == initial_version
                window.demo_change()
            elif window.result and checks['first_analysis'] and window.detector.version > initial_version:
                checks['changed_analysis'] = True
                window.grab().save(str(Path(__file__).parent / '介面預覽.png'))
                (Path(__file__).parent / '驗證結果.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
                print(json.dumps(checks, ensure_ascii=False))
                timer.stop()
                window.close()
                app.exit(0 if all(checks.values()) else 1)
            if elapsed[0] > 90000:
                print('介面驗證逾時：', window.statusBar().currentMessage())
                timer.stop()
                window.close()
                app.exit(1)
        timer.timeout.connect(poll)
        timer.start(100)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
