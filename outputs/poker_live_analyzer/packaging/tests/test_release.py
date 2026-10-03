import base64
import importlib.util
import json
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(tmp_path):
    version = tmp_path / 'version'
    for relative in ('PokerLens.exe', '_internal/python314.dll', 'assets/fonts/font.ttf'):
        file = version / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(relative.encode())
    return version


def test_signed_packages_and_reuse(tmp_path):
    packager = load('package_updates')
    verifier = load('verify_release')
    version = fixture(tmp_path)
    product = {'app_id': 'PokerLens', 'version': '1.0.0'}
    path = packager.package(version, tmp_path / 'release', product, 'https://github.com/owner/repo/releases/download/v1.0.0')
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    path.with_suffix('.sig').write_bytes(base64.b64encode(key.sign(path.read_bytes())))
    first = verifier.verify(path, public)
    product['version'] = '1.0.1'
    second = json.loads(packager.package(version, tmp_path / 'next', product, 'https://github.com/owner/repo/releases/download/v1.0.1', first).read_text(encoding='utf-8'))
    assert second['components'] == first['components']
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(InvalidSignature):
        verifier.verify(path, public)


def test_private_data_rejected(tmp_path):
    packager = load('package_updates')
    version = fixture(tmp_path)
    (version / 'data').mkdir()
    (version / 'data/private.json').write_text('{}')
    with pytest.raises(ValueError, match='禁止打包'):
        packager.package(version, tmp_path / 'release', {'app_id': 'PokerLens', 'version': '1.0.0'})


def test_modified_component_rejected(tmp_path):
    packager = load('package_updates')
    verifier = load('verify_release')
    path = packager.package(fixture(tmp_path), tmp_path / 'release', {'app_id': 'PokerLens', 'version': '1.0.0'}, 'https://github.com/owner/repo/releases/download/v1.0.0')
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    path.with_suffix('.sig').write_bytes(base64.b64encode(key.sign(path.read_bytes())))
    archive = next(path.parent.glob('PokerLens-app-*.zip'))
    original = bytearray(archive.read_bytes())
    original[0] ^= 1
    archive.write_bytes(original)
    with pytest.raises(ValueError, match='雜湊錯誤'):
        verifier.verify(path, public)
