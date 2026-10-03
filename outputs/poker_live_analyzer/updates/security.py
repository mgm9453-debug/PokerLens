from __future__ import annotations
import base64
import hashlib
import json
import re
import stat
import zipfile
from dataclasses import dataclass
from functools import total_ordering
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

MAX_MANIFEST = 256 * 1024
MAX_DOWNLOAD = 2 * 1024**3
MAX_EXPANDED = 4 * 1024**3
ALLOWED_HOSTS = {'api.github.com', 'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}

class UpdateError(RuntimeError):
    pass

@total_ordering
class Version:
    def __init__(self, value):
        match = re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?', value)
        if not match:
            raise UpdateError('版本格式不符合語意化版本規範')
        self.core = tuple(int(match[i]) for i in (1, 2, 3))
        self.pre = tuple(match[4].split('.')) if match[4] else ()
        if any(x.isdigit() and len(x) > 1 and x[0] == '0' for x in self.pre):
            raise UpdateError('預發行版本數字不可有前置零')
    def __eq__(self, other):
        return isinstance(other, Version) and (self.core, self.pre) == (other.core, other.pre)
    def __lt__(self, other):
        if self.core != other.core:
            return self.core < other.core
        if not self.pre or not other.pre:
            return bool(self.pre) and not other.pre
        for left, right in zip(self.pre, other.pre):
            if left == right:
                continue
            if left.isdigit() and right.isdigit():
                return int(left) < int(right)
            if left.isdigit() != right.isdigit():
                return left.isdigit()
            return left < right
        return len(self.pre) < len(other.pre)

def parse_version(value):
    if not isinstance(value, str) or len(value) > 128:
        raise UpdateError('版本格式無效')
    return Version(value)

def validate_url(value):
    if not isinstance(value, str) or any(ord(c) < 33 for c in value):
        raise UpdateError('下載網址無效')
    try:
        url = urlsplit(value)
        valid = url.scheme == 'https' and url.hostname in ALLOWED_HOSTS and url.port in (None, 443) and not url.username and not url.password and not url.fragment
    except ValueError:
        valid = False
    if not valid:
        raise UpdateError('下載網址必須是核准的 GitHub HTTPS 網址')
    return value

@dataclass(frozen=True)
class Component:
    name: str
    url: str
    sha256: str
    size: int

@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    components: tuple[Component, ...]
    manifest: bytes
    signature: bytes
    notes: str = ''

def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise UpdateError('清單包含重複欄位')
        result[key] = value
    return result

def verify_manifest(body, signature, public_key, app_id):
    if len(body) > MAX_MANIFEST or len(signature) > 1024 or not public_key:
        raise UpdateError('更新公鑰或清單大小無效，拒絕更新')
    try:
        key = base64.b64decode(public_key, validate=True)
        sig = base64.b64decode(signature.strip(), validate=True)
        Ed25519PublicKey.from_public_bytes(key).verify(sig, body)
    except Exception as exc:
        raise UpdateError('更新清單簽章驗證失敗') from exc
    try:
        data = json.loads(body.decode('utf-8'), object_pairs_hook=_unique_object)
        if type(data['schema']) is not int or data['schema'] != 1 or data['app_id'] != app_id:
            raise UpdateError('更新清單產品或結構不符')
        parse_version(data['version'])
        values = data.get('components')
        if values is None:
            values = {'app': data}
        elif not isinstance(values, dict) or set(values) != {'app', 'runtime', 'resources'}:
            raise UpdateError('更新清單缺少必要元件')
        components = []
        for name, entry in values.items():
            digest, size = entry['sha256'], entry['size']
            if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
                raise UpdateError('更新雜湊格式無效')
            if type(size) is not int or not 0 < size <= MAX_DOWNLOAD:
                raise UpdateError('更新檔案大小無效')
            components.append(Component(name, validate_url(entry['url']), digest, size))
        return ReleaseInfo(data['version'], tuple(components), body, signature)
    except UpdateError:
        raise
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise UpdateError('已驗簽更新清單格式無效') from exc

def verify_file(path, component):
    if Path(path).stat().st_size != component.size:
        raise UpdateError('下載檔案大小或雜湊不符')
    digest = hashlib.sha256()
    count = 0
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            count += len(block)
            if count > component.size:
                raise UpdateError('下載檔案大小或雜湊不符')
            digest.update(block)
    if count != component.size or digest.hexdigest() != component.sha256:
        raise UpdateError('下載檔案大小或雜湊不符')

def extract_archive(archive, destination):
    root = Path(destination)
    reserved = {'CON','PRN','AUX','NUL', *(f'COM{x}' for x in range(1,10)), *(f'LPT{x}' for x in range(1,10))}
    try:
        with zipfile.ZipFile(archive) as zipped:
            entries = zipped.infolist()
            if len(entries) > 20000 or sum(x.file_size for x in entries) > MAX_EXPANDED:
                raise UpdateError('更新壓縮檔超出展開限制')
            seen = set()
            for entry in entries:
                path = PurePosixPath(entry.filename)
                parts = entry.filename.rstrip('/').split('/')
                mode = entry.external_attr >> 16
                invalid = path.is_absolute() or '\\' in entry.orig_filename or '\x00' in entry.orig_filename or not parts or any(p in ('', '.', '..') or ':' in p or p.rstrip(' .') != p or p.split('.')[0].upper() in reserved or any(ord(c)<32 for c in p) for p in parts)
                if invalid or stat.S_ISLNK(mode) or (mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                    raise UpdateError('更新壓縮檔包含不安全路徑或連結')
                normalized = '/'.join(parts).casefold()
                if normalized in seen or entry.file_size > 1024**3 or entry.file_size > max(1024*1024, entry.compress_size*200):
                    raise UpdateError('更新壓縮檔包含重複路徑或異常壓縮比例')
                seen.add(normalized)
                target = root.joinpath(*parts)
                if not target.resolve().is_relative_to(root.resolve()) or (target.exists() and not (entry.is_dir() and target.is_dir())):
                    raise UpdateError('更新解壓目的地衝突或超出範圍')
            for entry in entries:
                target = root.joinpath(*PurePosixPath(entry.filename).parts)
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(entry) as source, target.open('xb') as output:
                    remaining = entry.file_size
                    while remaining:
                        block = source.read(min(1024*1024, remaining))
                        if not block:
                            raise UpdateError('更新壓縮檔資料截斷')
                        output.write(block)
                        remaining -= len(block)
                    if source.read(1):
                        raise UpdateError('更新壓縮檔展開大小不符')
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError('更新壓縮檔無法安全解壓') from exc
