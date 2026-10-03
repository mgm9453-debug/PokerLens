import argparse
import base64
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def verify(manifest_path, public_key):
    raw = manifest_path.read_bytes()
    signature = base64.b64decode(manifest_path.with_suffix('.sig').read_bytes().strip(), validate=True)
    Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key, validate=True)).verify(signature, raw)
    manifest = json.loads(raw)
    if manifest['schema'] != 1 or manifest.get('app_id') != 'PokerLens' or set(manifest['components']) != {'app', 'runtime', 'resources'}:
        raise ValueError('發布清單元件不完整')
    seen = set()
    for component in manifest['components'].values():
        url = urlparse(component['url'])
        if url.scheme != 'https' or url.hostname != 'github.com' or '/releases/download/' not in url.path or url.username or url.password or url.fragment:
            raise ValueError('發布元件必須使用 GitHub 官方 HTTPS 資產網址')
        path = manifest_path.parent / Path(urlparse(component['url']).path).name
        if path.stat().st_size != component['size']:
            raise ValueError('元件大小錯誤')
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != component['sha256']:
                raise ValueError('元件雜湊錯誤')
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                relative = PurePosixPath(entry.filename)
                if relative.is_absolute() or '..' in relative.parts or '\\' in entry.filename or ':' in entry.filename or entry.filename in seen:
                    raise ValueError('元件含有不安全或重複路徑')
                if relative.parts[0] in {'data', 'training', 'tests'} or 'tests' in relative.parts or 'testing' in relative.parts:
                    raise ValueError('元件含有禁止發布資料')
                seen.add(entry.filename)
            if archive.testzip():
                raise ValueError('元件壓縮檔损壞')
    if 'PokerLens.exe' not in seen:
        raise ValueError('缺少主程式')
    installer = manifest.get('installer')
    if installer:
        path = manifest_path.parent / Path(urlparse(installer['url']).path).name
        with path.open('rb') as stream:
            if path.stat().st_size != installer['size'] or hashlib.file_digest(stream, 'sha256').hexdigest() != installer['sha256']:
                raise ValueError('安裝程式大小或雜湊錯誤')
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--public-key', default='')
    args = parser.parse_args()
    product = json.loads((Path(__file__).resolve().parents[1] / 'release/product.json').read_text(encoding='utf-8'))
    verify(args.manifest, args.public_key or product['update_public_key'])
    print('發布清單簽章、元件雜湊與封裝內容驗證通過')


if __name__ == '__main__':
    main()
