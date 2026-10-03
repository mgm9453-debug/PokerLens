import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def package(version_dir, output, product, base_url='', previous=None):
    output.mkdir(parents=True, exist_ok=True)
    for group in ('app', 'runtime', 'resources'):
        for stale in output.glob(f'PokerLens-{group}-*.zip'):
            stale.unlink()
    (output / 'manifest.sig').unlink(missing_ok=True)
    groups = {'app': [], 'runtime': [], 'resources': []}
    for file in sorted(version_dir.rglob('*')):
        if not file.is_file():
            continue
        relative = file.relative_to(version_dir)
        if relative.parts[0] in {'data', 'training', 'tests', '.pytest_cache'} or 'tests' in relative.parts or 'testing' in relative.parts or file.suffix in {'.log', '.pyc'}:
            raise ValueError(f'禁止打包私人資料或測試：{relative}')
        group = 'runtime' if relative.parts[0] == '_internal' else 'resources' if relative.parts[0] in {'assets', 'models', 'config', 'profiles'} else 'app'
        groups[group].append((file, relative.as_posix()))
    manifest = {'schema': 1, 'app_id': product['app_id'], 'version': product['version'], 'components': {}}
    notes = ROOT / 'release/notes.md'
    if notes.exists():
        manifest['notes'] = notes.read_text(encoding='utf-8')[:20000]
    installer = output / f'PokerLens-Setup-{product["version"]}.exe'
    if installer.exists():
        manifest['installer'] = {'url': f'{base_url.rstrip("/")}/{installer.name}' if base_url else installer.name,
                                 'sha256': digest(installer), 'size': installer.stat().st_size}
    for group, files in groups.items():
        if not files:
            raise ValueError(f'元件沒有檔案：{group}')
        temporary = output / f'{group}.zip'
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for file, relative in files:
                info = zipfile.ZipInfo(relative, (2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, file.read_bytes())
        sha256 = digest(temporary)
        name = f'PokerLens-{group}-{sha256}.zip'
        destination = output / name
        temporary.replace(destination)
        prior = (previous or {}).get('components', {}).get(group, {})
        url = prior.get('url') if prior.get('sha256') == sha256 else f'{base_url.rstrip("/")}/{name}' if base_url else name
        manifest['components'][group] = {'url': url, 'sha256': sha256, 'size': destination.stat().st_size}
    path = output / 'manifest.json'
    path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version-dir', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/release')
    parser.add_argument('--base-url', default='')
    parser.add_argument('--previous-manifest', type=Path)
    args = parser.parse_args()
    product = json.loads((ROOT / 'release/product.json').read_text(encoding='utf-8'))
    previous = json.loads(args.previous_manifest.read_text(encoding='utf-8')) if args.previous_manifest else None
    package(args.version_dir or ROOT / 'dist/install-root/versions' / product['version'], args.output, product, args.base_url, previous)


if __name__ == '__main__':
    main()
