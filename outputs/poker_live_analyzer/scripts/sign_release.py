import argparse
import base64
import os
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--key-file', type=Path)
    args = parser.parse_args()
    secret = os.environ.get('POKERLENS_SIGNING_KEY', '')
    if not secret and args.key_file:
        secret = args.key_file.read_text(encoding='utf-8').strip()
    if not secret:
        raise SystemExit('未提供發布簽章金鑰；本機建置不會產生假簽章')
    if secret.startswith('-----BEGIN'):
        key = serialization.load_pem_private_key(secret.encode(), password=None)
    else:
        key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(secret, validate=True))
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit('發布金鑰必須為 Ed25519')
    args.manifest.with_suffix('.sig').write_bytes(base64.b64encode(key.sign(args.manifest.read_bytes())) + b'\n')


if __name__ == '__main__':
    main()
