from __future__ import annotations
import json
import logging
import os
import re
import shutil
import urllib.error
import urllib.request
import uuid
from dataclasses import replace
from pathlib import Path
from .security import Component, ReleaseInfo, UpdateError, MAX_MANIFEST, parse_version, validate_url, verify_manifest, verify_file, extract_archive
from .storage import atomic_json, installation_lock, load_state, wait_for_exit
from .backup import snapshot_user_data


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class UpdateClient:
    def __init__(self, product_path, install_root, user_data):
        self.product_path = Path(product_path)
        self.install_root = Path(install_root)
        self.user_data = Path(user_data)
        try:
            self.product = json.loads(self.product_path.read_text(encoding='utf-8-sig'))
            parse_version(self.product['version'])
            if self.product['app_id'] != 'PokerLens':
                raise ValueError()
        except (OSError, KeyError, ValueError, TypeError) as exc:
            raise UpdateError('產品更新設定無效') from exc
        self.opener = urllib.request.build_opener(SafeRedirect())

    def _open(self, url):
        request = urllib.request.Request(validate_url(url), headers={'User-Agent':'PokerLens-Updater', 'Accept':'application/vnd.github+json'})
        try:
            response = self.opener.open(request, timeout=30)
            validate_url(response.geturl())
            return response
        except (OSError, urllib.error.URLError) as exc:
            raise UpdateError('無法連線至更新伺服器') from exc

    def _read(self, url, maximum):
        with self._open(url) as response:
            data = response.read(maximum + 1)
        if len(data) > maximum:
            raise UpdateError('更新回應超出大小限制')
        return data

    def _verify(self, body, signature):
        return verify_manifest(body, signature, self.product.get('update_public_key', ''), self.product['app_id'])

    def check(self):
        repository = self.product.get('github_repository', '')
        if not repository or not self.product.get('update_public_key'):
            raise UpdateError('尚未設定 GitHub 儲存庫及更新公鑰，更新已停用')
        match = re.fullmatch(r'(?:https://github\.com/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?', repository)
        if not match or any(part in ('.','..') for part in match.groups()):
            raise UpdateError('GitHub 儲存庫格式無效')
        owner, repo = match.groups()
        self.repository = (owner, repo)
        try:
            release = json.loads(self._read(f'https://api.github.com/repos/{owner}/{repo}/releases/latest', 1024*1024))
            if release.get('draft') or release.get('prerelease'):
                return None
            assets = {asset['name']:asset['browser_download_url'] for asset in release['assets']}
            manifest_url = assets['manifest.json']
            signature_url = assets['manifest.sig']
            prefix = f'https://github.com/{owner}/{repo}/releases/download/'
            if not manifest_url.startswith(prefix) or not signature_url.startswith(prefix):
                raise UpdateError('清單資產來源不符合指定儲存庫')
            info = self._verify(self._read(manifest_url, MAX_MANIFEST), self._read(signature_url, 1024))
            if any(not entry.url.startswith(prefix) for entry in info.components):
                raise UpdateError('更新資產來源不符合指定儲存庫')
            if release.get('tag_name') != 'v' + info.version:
                raise UpdateError('發行標籤與已驗簽版本不符')
            notes = release.get('body')
            if isinstance(notes, str) and notes.strip():
                info = replace(info, notes=notes[:65536])
            current = load_state(self.install_root)['version'] if (self.install_root/'current.json').exists() else self.product['version']
            return info if parse_version(info.version) > parse_version(current) else None
        except (KeyError, ValueError, TypeError) as exc:
            raise UpdateError('GitHub 發行資料不完整') from exc

    def download(self, release, progress_callback=None):
        release = self._verify(release.manifest, release.signature)
        directory = self.user_data/'updates'/uuid.uuid4().hex
        directory.mkdir(parents=True)
        total = sum(c.size for c in release.components)
        received = 0
        try:
            for component in release.components:
                temporary = directory/(component.name + '.zip.part')
                cached = self._reuse_component(component, temporary)
                if cached:
                    received += component.size
                    if progress_callback:
                        progress_callback(received, total)
                    os.replace(temporary, directory/(component.name + '.zip'))
                    continue
                with self._open(component.url) as response, temporary.open('xb') as output:
                    count = 0
                    while True:
                        block = response.read(min(1024*1024, component.size-count+1))
                        if not block:
                            break
                        count += len(block)
                        if count > component.size:
                            raise UpdateError('下載檔案超出清單大小')
                        output.write(block)
                        received += len(block)
                        if progress_callback:
                            progress_callback(received, total)
                    output.flush()
                    os.fsync(output.fileno())
                verify_file(temporary, component)
                os.replace(temporary, directory/(component.name + '.zip'))
                self._save_component(component, directory/(component.name + '.zip'))
            (directory/'manifest.json').write_bytes(release.manifest)
            (directory/'manifest.sig').write_bytes(release.signature)
            return directory
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise

    def _reuse_component(self, component, temporary):
        candidates = (
            self.user_data/'cache'/'components'/(component.sha256+'.zip'),
            self.install_root/'component-cache'/(component.sha256+'.zip'),
        )
        for candidate in candidates:
            try:
                verify_file(candidate, component)
                shutil.copyfile(candidate, temporary)
                # 複製後再驗證，避免快取於讀取期間被替換。
                verify_file(temporary, component)
                logging.info('已重用通過驗證的元件快取：%s', component.name)
                return True
            except (OSError, UpdateError):
                temporary.unlink(missing_ok=True)
        return False

    def _save_component(self, component, archive):
        cache = self.user_data/'cache'/'components'
        temporary = cache/(component.sha256+'.'+uuid.uuid4().hex+'.part')
        try:
            cache.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(archive, temporary)
            verify_file(temporary, component)
            with temporary.open('r+b') as stream:
                os.fsync(stream.fileno())
            os.replace(temporary, cache/(component.sha256+'.zip'))
        except (OSError, UpdateError):
            # 快取失敗不影響已完成驗證的本次下載。
            logging.warning('元件快取無法保存，本次下載仍可使用')
        finally:
            temporary.unlink(missing_ok=True)

    def package(self, directory):
        directory = Path(directory)
        with (directory/'manifest.json').open('rb') as source:
            body = source.read(MAX_MANIFEST + 1)
        with (directory/'manifest.sig').open('rb') as source:
            signature = source.read(1025)
        return self._verify(body, signature)

    def install(self, release, package_path, wait_pid=None):
        release = self._verify(release.manifest, release.signature)
        package_path = Path(package_path)
        wait_for_exit(wait_pid)
        with installation_lock(self.install_root, timeout=10):
            state = load_state(self.install_root)
            if state.get('pending'):
                raise UpdateError('目前版本尚未通過健康檢查')
            if parse_version(release.version) <= parse_version(state['version']):
                raise UpdateError('更新版本必須高於目前版本')
            versions = self.install_root/'versions'
            versions.mkdir(parents=True, exist_ok=True)
            destination = versions/release.version
            if destination.exists():
                raise UpdateError('更新版本目錄已存在，拒絕覆蓋')
            staging = versions/('.staging-' + uuid.uuid4().hex)
            staging.mkdir()
            promoted = False
            try:
                for component in release.components:
                    archive = package_path/(component.name+'.zip')
                    verify_file(archive, component)
                    extract_archive(archive, staging)
                if not (staging/'PokerLens.exe').is_file():
                    raise UpdateError('更新版本缺少主程式')
                snapshot_user_data(self.user_data, state['version'], release.version)
                os.replace(staging, destination)
                promoted = True
                atomic_json(self.install_root/'current.json', {'version':release.version, 'previous':state['version'], 'pending':True})
                logging.info('更新已準備完成，等待啟動健康檢查')
                return destination
            except Exception:
                shutil.rmtree(destination if promoted else staging, ignore_errors=True)
                raise
