import json
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(SPECPATH).parent
product = json.loads((root / 'release/product.json').read_text(encoding='utf-8'))
entry = os.environ.get('POKERLENS_ENTRY', 'app')
name = {'app': 'PokerLens', 'launcher': 'Launcher', 'updater': 'Updater'}[entry]
datas = [(str(root / 'release/product.json'), 'release')]
binaries = []
hiddenimports = collect_submodules('updates')
modules = ['cryptography']
if entry == 'app':
    modules += ['PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'windows_capture', 'winrt', 'cv2', 'mss', 'numpy', 'treys', 'yaml']
for module in modules:
    extra_datas, extra_binaries, extra_imports = collect_all(module, filter_submodules=lambda name: not any(part in {'tests', 'testing'} or part.endswith('_tests') or part.startswith('test_') for part in name.split('.')))
    datas += [(source, destination) for source, destination in extra_datas
              if not any(part in {'tests', 'testing', '__pycache__'} for part in Path(source).parts)]
    binaries += extra_binaries
    hiddenimports += extra_imports
if entry == 'app':
    for module in ['winrt.windows.foundation', 'winrt.windows.foundation.collections',
                   'winrt.windows.globalization', 'winrt.windows.graphics.imaging',
                   'winrt.windows.media.ocr', 'winrt.windows.storage.streams']:
        hiddenimports += collect_submodules(module)
icon = root / 'assets/PokerLens.ico'
a = Analysis([str(root / (entry + '.py'))], pathex=[str(root)], binaries=binaries,
             datas=datas, hiddenimports=hiddenimports, excludes=['pytest', '_pytest', 'training', 'tests', 'numpy.tests', 'numpy.testing'],
             noarchive=False)
# Qt 使用 Windows 內建 ICU；排除環境搜尋路徑中的同名第三方 ICU。
a.binaries = [item for item in a.binaries if Path(item[0]).name.lower() != 'icuuc.dll' and not Path(item[0]).name.lower().startswith('icudt')]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=name, console=os.environ.get('POKERLENS_DIAGNOSTIC') == '1',
          icon=str(icon) if icon.exists() else None, version=str(root / 'packaging/version_info.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=name)
