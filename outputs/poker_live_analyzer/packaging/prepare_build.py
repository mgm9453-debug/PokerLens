import argparse
import json
import importlib.metadata
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def normalize_library(path):
    with zipfile.ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, value in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, value)


def collect_licenses(version_dir):
    destination = version_dir / 'assets/licenses'
    destination.mkdir(parents=True, exist_ok=True)
    names = ['PySide6', 'PySide6-Addons', 'PySide6-Essentials', 'shiboken6',
             'opencv-python', 'numpy', 'mss', 'windows-capture', 'treys', 'PyYAML',
             'cryptography', 'cffi', 'pycparser', 'typing_extensions', 'winrt-runtime',
             'winrt-Windows.Foundation', 'winrt-Windows.Foundation.Collections',
             'winrt-Windows.Globalization', 'winrt-Windows.Graphics.Imaging',
             'winrt-Windows.Media.Ocr', 'winrt-Windows.Storage.Streams']
    lines = ['# 第三方授權索引', '', '以下保留相依套件原始授權文字；字體授權另見 assets/fonts。', '']
    for name in names:
        distribution = importlib.metadata.distribution(name)
        files = []
        for item in distribution.files or []:
            if not Path(item).name.upper().startswith(('LICENSE', 'LICENCE', 'COPYING', 'NOTICE')):
                continue
            source = Path(distribution.locate_file(item))
            if not source.is_file():
                continue
            target = destination / name / Path(item).name
            target.parent.mkdir(exist_ok=True)
            if target.exists() and target.read_bytes() != source.read_bytes():
                target = target.with_name(str(len(files)) + '-' + target.name)
            shutil.copy2(source, target)
            files.append(target.relative_to(version_dir).as_posix())
        if not files:
            target = destination / name / '套件授權資訊.txt'
            target.parent.mkdir(exist_ok=True)
            target.write_text('\n'.join(f'{key}: {value}' for key, value in distribution.metadata.items()), encoding='utf-8')
            files.append(target.relative_to(version_dir).as_posix())
            if name.lower().startswith('winrt-'):
                license_target = target.parent / 'LICENSE.txt'
                shutil.copy2(ROOT / 'packaging/PyWinRT-LICENSE.txt', license_target)
                files.append(license_target.relative_to(version_dir).as_posix())
        lines.append(f'- `{name}`：版本 `{distribution.version}`；授權位置：' + '、'.join(f'`{file}`' for file in files))
    (destination / '第三方授權索引.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def assemble(product):
    target = ROOT / 'dist/install-root'
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    version_dir = target / 'versions' / product['version']
    shutil.copytree(ROOT / 'dist/frozen/PokerLens', version_dir)
    shutil.move(str(version_dir / '_internal/release'), str(version_dir / 'release'))
    shutil.copy2(ROOT / 'release/product.json', version_dir / 'release/product.json')
    normalize_library(version_dir / '_internal/base_library.zip')
    for directory in ('assets', 'models', 'config'):
        source = ROOT / directory
        if source.exists():
            shutil.copytree(source, version_dir / directory,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.log'))
    collect_licenses(version_dir)
    for name in ('Launcher', 'Updater'):
        source = ROOT / 'dist/frozen' / name
        for item in source.rglob('*'):
            if not item.is_file():
                continue
            if item.relative_to(source).parts[:2] == ('_internal', 'release'):
                continue
            destination = target / item.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and destination.read_bytes() != item.read_bytes():
                if item.name == 'base_library.zip':
                    with zipfile.ZipFile(destination) as first, zipfile.ZipFile(item) as second:
                        entries = {name: first.read(name) for name in first.namelist()}
                        for entry in second.namelist():
                            value = second.read(entry)
                            if entry in entries and entries[entry] != value:
                                raise ValueError(f'啟動器標準函式庫衝突：{entry}')
                            entries[entry] = value
                    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as merged:
                        for entry, value in sorted(entries.items()):
                            merged.writestr(zipfile.ZipInfo(entry, (2020, 1, 1, 0, 0, 0)), value)
                    continue
                raise ValueError(f'啟動器相依套件衝突：{destination}')
            shutil.copy2(item, destination)
    (target / 'release').mkdir()
    shutil.copy2(ROOT / 'release/product.json', target / 'release/product.json')
    (target / 'current.json').write_text(json.dumps({'version': product['version'], 'previous': None, 'pending': False}) + '\n', encoding='utf-8')
    sys.path.insert(0, str(ROOT))
    from scripts.package_updates import package
    cache_output = ROOT / 'dist/cache-seed'
    if cache_output.exists():
        shutil.rmtree(cache_output)
    manifest_path = package(version_dir, cache_output, product)
    components = json.loads(manifest_path.read_text(encoding='utf-8'))['components']
    cache = target / 'component-cache'
    cache.mkdir()
    for name in ('runtime', 'resources'):
        item = components[name]
        shutil.copy2(cache_output / item['url'], cache / (item['sha256'] + '.zip'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--assemble', action='store_true')
    args = parser.parse_args()
    product = json.loads((ROOT / 'release/product.json').read_text(encoding='utf-8'))
    if args.assemble:
        assemble(product)
        return
    version = tuple(int(part) for part in product['version'].split('.')) + (0,)
    value = f'''VSVersionInfo(ffi=FixedFileInfo(filevers={version!r}, prodvers={version!r}, mask=0x3f, flags=0, OS=0x40004, fileType=0x1, subtype=0, date=(0, 0)), kids=[StringFileInfo([StringTable('040904B0', [StringStruct('CompanyName', {product['publisher']!r}), StringStruct('FileDescription', {product['name']!r}), StringStruct('FileVersion', {product['version']!r}), StringStruct('ProductName', {product['name']!r}), StringStruct('ProductVersion', {product['version']!r})])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])'''
    (ROOT / 'packaging/version_info.txt').write_text(value, encoding='utf-8')


if __name__ == '__main__':
    main()
