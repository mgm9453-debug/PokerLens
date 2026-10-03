"""初次發布建立私鑰，存於專案以外；客戶端只持有公鑰。"""
import base64
import json
import os
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

def main():
    directory = Path(os.environ['LOCALAPPDATA']) / 'PokerLensRelease'
    directory.mkdir(parents=True, exist_ok=True)
    private_path = directory / 'signing.key'
    if private_path.is_file():
        key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_path.read_bytes(), validate=True))
    else:
        key = Ed25519PrivateKey.generate()
        private_path.write_bytes(base64.b64encode(key.private_bytes(serialization.Encoding.Raw,
                                   serialization.PrivateFormat.Raw, serialization.NoEncryption())))
    public = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,
                              serialization.PublicFormat.Raw)).decode('ascii')
    path = Path(__file__).resolve().parents[1] / 'release' / 'product.json'
    product = json.loads(path.read_text(encoding='utf-8'))
    existing = product.get('update_public_key')
    if existing and existing != public:
        raise SystemExit('產品公鑰與本機私鑰不同，已拒絕覆寫，請先確認原始發布私鑰。')
    product['update_public_key'] = public
    path.write_text(json.dumps(product, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('已建立發布簽章設定。私鑰保存在專案以外，請另行安全備份。')

if __name__ == '__main__':
    main()
