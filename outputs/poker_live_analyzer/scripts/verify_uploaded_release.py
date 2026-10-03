"""公開前核對 GitHub 草稿資產，避免缺檔或上傳內容不一致。"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def verify_uploaded(directory, release, tag):
    if release.get('tag_name') != tag or release.get('draft') is not True:
        raise ValueError('只允許驗證指定版本的未公開草稿')
    files = {path.name: path for path in Path(directory).iterdir() if path.is_file()}
    assets = release.get('assets', [])
    names = [asset['name'] for asset in assets]
    if len(names) != len(set(names)) or set(names) != set(files):
        raise ValueError('遠端資產缺漏、重複或包含多餘檔案')
    for asset in assets:
        path = files[asset['name']]
        with path.open('rb') as stream:
            digest = 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()
        if asset.get('state') != 'uploaded' or asset.get('size') != path.stat().st_size or asset.get('digest') != digest:
            raise ValueError('遠端資產尚未完成，或大小與雜湊不符：' + path.name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repository', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    result = subprocess.run(['gh', 'api', f'repos/{args.repository}/releases/tags/{args.tag}'],
                            check=True, capture_output=True)
    verify_uploaded(args.directory, json.loads(result.stdout), args.tag)
    print('遠端草稿資產數量、狀態、大小及 SHA-256 均通過驗證')


if __name__ == '__main__':
    main()
