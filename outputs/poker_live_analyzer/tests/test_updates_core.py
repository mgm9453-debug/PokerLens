import base64
import io
import json
import zipfile
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from updates.security import UpdateError, parse_version, verify_manifest, validate_url, extract_archive
from updates.storage import atomic_json, load_state, rollback


def test_versions():
    assert parse_version('1.10.0') > parse_version('1.9.0')
    assert parse_version('1.0.0') > parse_version('1.0.0-rc.2')
    assert parse_version('1.0.0-rc.10') > parse_version('1.0.0-rc.2')
    for value in ['v1.0.0', '01.0.0', '1.0', '1.0.0-01', '../1.0.0']:
        with pytest.raises(UpdateError):
            parse_version(value)


def test_signature_before_json():
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    body = b'{"schema":1,"app_id":"PokerLens","version":"1.1.0","url":"https://github.com/a/b/releases/download/v1.1.0/app.zip","sha256":"' + b'a'*64 + b'","size":12}'
    signature = base64.b64encode(key.sign(body))
    assert verify_manifest(body, signature, public, 'PokerLens').version == '1.1.0'
    with pytest.raises(UpdateError, match='簽章'):
        verify_manifest(b'not-json', signature, public, 'PokerLens')
    with pytest.raises(UpdateError):
        verify_manifest(body, signature, '', 'PokerLens')


@pytest.mark.parametrize('url', ['http://github.com/a', 'https://github.com.evil/a', 'https://user@github.com/a', 'https://github.com:8443/a', 'https://localhost/a'])
def test_reject_urls(url):
    with pytest.raises(UpdateError):
        validate_url(url)


@pytest.mark.parametrize('name', ['../evil.exe', '/evil.exe', 'C:/evil.exe', 'x/../../evil', 'x\\evil.exe', 'CON', 'a:stream'])
def test_zip_traversal(tmp_path, name):
    archive = tmp_path/'bad.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr(name.replace(chr(92), '/'), b'x')
    if chr(92) in name:
        archive.write_bytes(archive.read_bytes().replace(name.replace(chr(92), '/').encode(), name.encode()))
    with pytest.raises(UpdateError):
        extract_archive(archive, tmp_path/'target')
    assert not (tmp_path/'evil.exe').exists()


def test_zip_symlink(tmp_path):
    archive = tmp_path/'bad.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        info = zipfile.ZipInfo('link')
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        z.writestr(info, 'outside')
    with pytest.raises(UpdateError):
        extract_archive(archive, tmp_path/'target')


def test_rollback(tmp_path):
    atomic_json(tmp_path/'current.json', {'version':'1.1.0', 'previous':'1.0.0', 'pending':True})
    rollback(tmp_path)
    assert load_state(tmp_path)['version'] == '1.0.0'

def test_install_keeps_old_pointer_on_bad_hash(tmp_path):
    from updates.client import UpdateClient
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    product = tmp_path/'product.json'
    product.write_text(json.dumps({'version':'1.0.0','app_id':'PokerLens','update_public_key':public}))
    atomic_json(tmp_path/'current.json', {'version':'1.0.0','previous':None,'pending':False})
    archive = tmp_path/'app.zip'
    archive.write_bytes(b'wrong')
    body = json.dumps({'schema':1,'app_id':'PokerLens','version':'1.1.0','url':'https://github.com/a/b/releases/download/v1.1.0/app.zip','sha256':'a'*64,'size':5}).encode()
    release = verify_manifest(body, base64.b64encode(key.sign(body)), public, 'PokerLens')
    client = UpdateClient(product, tmp_path, tmp_path/'data')
    with pytest.raises(UpdateError):
        client.install(release, tmp_path)
    assert load_state(tmp_path)['version'] == '1.0.0'
    assert not (tmp_path/'versions'/'1.1.0').exists()


def test_health_handshake(tmp_path, monkeypatch):
    from updates.health import report_healthy, is_healthy
    monkeypatch.setenv('POKERLENS_HEALTH_PATH', str(tmp_path/'health.json'))
    monkeypatch.setenv('POKERLENS_HEALTH_TOKEN', 'token')
    report_healthy()
    assert is_healthy(tmp_path/'health.json', 'token', __import__('os').getpid())
    assert not is_healthy(tmp_path/'health.json', 'different', __import__('os').getpid())

def test_download_cancel_cleans_partial(tmp_path):
    from updates.client import UpdateClient
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    product = tmp_path/'product.json'
    product.write_text(json.dumps({'version':'1.0.0','app_id':'PokerLens','update_public_key':public}))
    payload = b'hello'
    body = json.dumps({'schema':1,'app_id':'PokerLens','version':'1.1.0','url':'https://github.com/a/b/releases/download/v1.1.0/app.zip','sha256':__import__('hashlib').sha256(payload).hexdigest(),'size':5}).encode()
    release = verify_manifest(body, base64.b64encode(key.sign(body)), public, 'PokerLens')
    client = UpdateClient(product, tmp_path, tmp_path/'data')
    client._open = lambda url: io.BytesIO(payload)
    def cancel(received, total):
        raise RuntimeError('使用者取消下載')
    with pytest.raises(RuntimeError):
        client.download(release, cancel)
    assert list((tmp_path/'data'/'updates').iterdir()) == []


def test_install_valid_package(tmp_path):
    from updates.client import UpdateClient
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    product = tmp_path/'product.json'
    product.write_text(json.dumps({'version':'1.0.0','app_id':'PokerLens','update_public_key':public}))
    atomic_json(tmp_path/'current.json', {'version':'1.0.0','previous':None,'pending':False})
    archive = tmp_path/'app.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('PokerLens.exe', '執行檔'.encode())
    payload = archive.read_bytes()
    body = json.dumps({'schema':1,'app_id':'PokerLens','version':'1.1.0','url':'https://github.com/a/b/releases/download/v1.1.0/app.zip','sha256':__import__('hashlib').sha256(payload).hexdigest(),'size':len(payload)}).encode()
    release = verify_manifest(body, base64.b64encode(key.sign(body)), public, 'PokerLens')
    client = UpdateClient(product, tmp_path, tmp_path/'data')
    client.install(release, tmp_path)
    assert load_state(tmp_path) == {'version':'1.1.0','previous':'1.0.0','pending':True}
    assert (tmp_path/'versions'/'1.1.0'/'PokerLens.exe').is_file()


def test_launcher_rolls_back_early_crash(tmp_path):
    from updates.runner import launch
    atomic_json(tmp_path/'current.json', {'version':'1.1.0','previous':'1.0.0','pending':True})
    for version in ('1.1.0', '1.0.0'):
        directory = tmp_path/'versions'/version
        directory.mkdir(parents=True)
        (directory/'PokerLens.exe').write_bytes('執行檔'.encode())
    launches = []
    class Process:
        pid = 123
        def __init__(self, result): self.result = result
        def poll(self): return self.result
        def wait(self): return self.result
    def factory(args, cwd, env):
        launches.append(cwd.name)
        if cwd.name == '1.0.0':
            atomic_json(env['POKERLENS_HEALTH_PATH'], {'token':env['POKERLENS_HEALTH_TOKEN'],'pid':123})
            return Process(0)
        return Process(1)
    assert launch(tmp_path, tmp_path/'data', process_factory=factory) == 0
    assert launches == ['1.1.0','1.0.0']
    assert load_state(tmp_path)['version'] == '1.0.0'


def test_zip_bomb(tmp_path):
    archive = tmp_path/'bomb.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('large', b'0' * (2*1024*1024))
    with pytest.raises(UpdateError):
        extract_archive(archive, tmp_path/'target')

def test_launcher_rolls_back_after_health_crash(tmp_path):
    from updates.runner import launch
    atomic_json(tmp_path/'current.json', {'version':'1.1.0','previous':'1.0.0','pending':True})
    for version in ('1.1.0', '1.0.0'):
        directory = tmp_path/'versions'/version
        directory.mkdir(parents=True)
        (directory/'PokerLens.exe').write_bytes(b'x')
    class Process:
        pid = 123
        def __init__(self, result): self.result = result
        def poll(self): return None
        def wait(self): return self.result
    def factory(args, cwd, env):
        atomic_json(env['POKERLENS_HEALTH_PATH'], {'token':env['POKERLENS_HEALTH_TOKEN'],'pid':123})
        return Process(1 if cwd.name == '1.1.0' else 0)
    assert launch(tmp_path, tmp_path/'data', process_factory=factory) == 0
    assert load_state(tmp_path)['version'] == '1.0.0'


def test_launcher_rolls_back_missing_executable(tmp_path):
    from updates.runner import launch
    atomic_json(tmp_path/'current.json', {'version':'1.1.0','previous':'1.0.0','pending':True})
    directory = tmp_path/'versions'/'1.0.0'
    directory.mkdir(parents=True)
    (directory/'PokerLens.exe').write_bytes(b'x')
    class Process:
        pid = 123
        def poll(self): return 0
        def wait(self): return 0
    def factory(args, cwd, env):
        atomic_json(env['POKERLENS_HEALTH_PATH'], {'token':env['POKERLENS_HEALTH_TOKEN'],'pid':123})
        return Process()
    assert launch(tmp_path, tmp_path/'data', process_factory=factory) == 0
    assert load_state(tmp_path)['version'] == '1.0.0'


def test_launcher_timeout_keeps_running_process(tmp_path):
    from updates.runner import launch
    atomic_json(tmp_path/'current.json', {'version':'1.1.0','previous':'1.0.0','pending':True})
    directory = tmp_path/'versions'/'1.1.0'
    directory.mkdir(parents=True)
    (directory/'PokerLens.exe').write_bytes(b'x')
    class Process:
        pid = 123
        def poll(self): return None
        def kill(self): pytest.fail('不應強殺程序')
        def terminate(self): pytest.fail('不應強制關閉程序')
    with pytest.raises(UpdateError, match='尚未結束'):
        launch(tmp_path, tmp_path/'data', health_timeout=0, process_factory=lambda *args, **kwargs:Process())
    assert load_state(tmp_path)['version'] == '1.0.0'


def test_redirect_rejects_unapproved_host():
    from updates.client import SafeRedirect
    import urllib.request
    with pytest.raises(UpdateError):
        SafeRedirect().redirect_request(urllib.request.Request('https://github.com/a'), None, 302, '', {}, 'https://evil.test/a')


def test_lock_prevents_parallel_switch(tmp_path):
    from updates.storage import installation_lock
    with installation_lock(tmp_path):
        with pytest.raises(UpdateError):
            with installation_lock(tmp_path):
                pytest.fail('不能同時取得更新鎖')


def test_multicomponent_shared_directory(tmp_path):
    for name in ('first','second'):
        archive = tmp_path/(name+'.zip')
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('assets/', '')
            z.writestr('assets/'+name+'.bin', b'x')
        extract_archive(archive, tmp_path/'target')
    assert (tmp_path/'target'/'assets'/'first.bin').is_file()
    assert (tmp_path/'target'/'assets'/'second.bin').is_file()

def test_check_uses_signed_version_and_rejects_downgrade(tmp_path):
    from updates.client import UpdateClient
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    product = tmp_path/'product.json'
    product.write_text(json.dumps({'version':'1.0.0','app_id':'PokerLens','update_public_key':public,'github_repository':'https://github.com/owner/repo'}))
    prefix = 'https://github.com/owner/repo/releases/download/v1.1.0/'
    body = json.dumps({'schema':1,'app_id':'PokerLens','version':'1.1.0','url':prefix+'app.zip','sha256':'a'*64,'size':12}).encode()
    release = json.dumps({'tag_name':'v1.1.0','assets':[{'name':'manifest.json','browser_download_url':prefix+'manifest.json'},{'name':'manifest.sig','browser_download_url':prefix+'manifest.sig'}]}).encode()
    signature = base64.b64encode(key.sign(body))
    client = UpdateClient(product, tmp_path, tmp_path/'data')
    client._read = lambda url, maximum: release if 'api.github.com' in url else signature if url.endswith('.sig') else body
    assert client.check().version == '1.1.0'
    remote = json.loads(release)
    remote['body'] = 'GitHub 新版說明'
    release = json.dumps(remote).encode()
    assert client.check().notes == 'GitHub 新版說明'
    remote['body'] = {'不合法': '說明'}
    release = json.dumps(remote).encode()
    assert client.check().notes == ''
    atomic_json(tmp_path/'current.json', {'version':'1.2.0','previous':None,'pending':False})
    assert client.check() is None


def test_missing_key_disables_updates(tmp_path):
    from updates.client import UpdateClient
    product = tmp_path/'product.json'
    product.write_text(json.dumps({'version':'1.0.0','app_id':'PokerLens','update_public_key':'','github_repository':''}))
    client = UpdateClient(product, tmp_path, tmp_path/'data')
    with pytest.raises(UpdateError, match='停用'):
        client.check()

def test_updater_failure_restarts_existing_version(tmp_path, monkeypatch):
    import updater
    import sys
    calls = []
    class Client:
        def __init__(self, *args): pass
        def package(self, path): raise UpdateError('簽章失敗')
    monkeypatch.setattr(updater, 'UpdateClient', Client)
    monkeypatch.setattr(updater, 'show_error', lambda message: None)
    monkeypatch.setattr(updater.subprocess, 'Popen', lambda args, **kwargs:calls.append(args))
    monkeypatch.setattr(sys, 'argv', ['updater','--product',str(tmp_path/'product.json'),'--root',str(tmp_path),'--data',str(tmp_path/'data'),'--package',str(tmp_path/'package')])
    assert updater.main() == 1
    assert calls[0][0] == str(tmp_path/'Launcher.exe')


def test_launcher_busy_activates_existing_window(tmp_path, monkeypatch):
    import launcher
    import sys
    def busy(*args): raise UpdateError('另一個啟動或更新程序正在處理')
    monkeypatch.setattr(launcher, 'launch', busy)
    monkeypatch.setattr(launcher, 'activate_existing', lambda directory:True)
    monkeypatch.setattr(launcher, 'show_error', lambda message:pytest.fail('已喚回視窗不應報錯'))
    monkeypatch.setattr(sys, 'argv', ['launcher','--root',str(tmp_path),'--data',str(tmp_path/'data')])
    assert launcher.main() == 0


def test_launcher_busy_passes_user_data_to_window_activation(tmp_path, monkeypatch):
    import launcher
    import sys
    calls=[]
    def busy(*args):raise UpdateError('另一個啟動或更新程序正在處理')
    monkeypatch.setattr(launcher,'launch',busy)
    monkeypatch.setattr(launcher,'activate_existing',lambda directory:calls.append(directory) or True)
    monkeypatch.setattr(launcher,'show_error',lambda message:pytest.fail('已喚回程式不應報錯'))
    directory=tmp_path/'data'
    monkeypatch.setattr(sys,'argv',['launcher','--root',str(tmp_path),'--data',str(directory)])
    assert launcher.main()==0
    assert calls==[directory]

def test_corrupt_health_file_is_not_accepted(tmp_path):
    from updates.health import is_healthy
    path = tmp_path/'health.json'
    path.write_text('[]')
    assert is_healthy(path, 'token', 123) is False

def make_cached_client(tmp_path):
    from updates.client import UpdateClient
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    product = tmp_path/'product.json'
    product.write_text(json.dumps({'version':'1.0.0','app_id':'PokerLens','update_public_key':public}))
    payload = b'unchanged-component'
    body = json.dumps({'schema':1,'app_id':'PokerLens','version':'1.1.0','url':'https://github.com/a/b/releases/download/v1.1.0/app.zip','sha256':__import__('hashlib').sha256(payload).hexdigest(),'size':len(payload)}).encode()
    release = verify_manifest(body, base64.b64encode(key.sign(body)), public, 'PokerLens')
    return UpdateClient(product, tmp_path, tmp_path/'data'), release, payload


def test_component_cache_second_download_never_connects(tmp_path):
    client, release, payload = make_cached_client(tmp_path)
    requests = []
    client._open = lambda url:(requests.append(url) or io.BytesIO(payload))
    client.download(release)
    assert len(requests) == 1
    progress = []
    client._open = lambda url:pytest.fail('相同元件不應再次連線')
    directory = client.download(release, lambda received,total:progress.append((received,total)))
    assert (directory/'app.zip').read_bytes() == payload
    assert progress[-1] == (len(payload), len(payload))


def test_corrupt_cache_falls_back_to_download(tmp_path):
    client, release, payload = make_cached_client(tmp_path)
    cache = client.user_data/'cache'/'components'/(release.components[0].sha256+'.zip')
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b'X' * len(payload))
    requests = []
    client._open = lambda url:(requests.append(url) or io.BytesIO(payload))
    directory = client.download(release)
    assert len(requests) == 1
    assert (directory/'app.zip').read_bytes() == payload
    assert cache.read_bytes() == payload


def test_installer_seed_cache_is_verified_and_reused(tmp_path):
    client, release, payload = make_cached_client(tmp_path)
    cache = client.install_root/'component-cache'/(release.components[0].sha256+'.zip')
    cache.parent.mkdir()
    cache.write_bytes(payload)
    client._open = lambda url:pytest.fail('有效安裝快取不應連線')
    assert (client.download(release)/'app.zip').read_bytes() == payload


def test_cancelled_download_never_saves_partial_cache(tmp_path):
    client, release, payload = make_cached_client(tmp_path)
    client._open = lambda url:io.BytesIO(payload)
    def cancel(received,total): raise RuntimeError('使用者取消下載')
    with pytest.raises(RuntimeError):
        client.download(release, cancel)
    assert not list(client.user_data.rglob('*.part'))
    assert not list((client.user_data/'cache').rglob('*.zip'))
    assert list((client.user_data/'updates').iterdir()) == []

def test_update_snapshot_preserves_original_contents(tmp_path):
    from updates.backup import snapshot_user_data
    import sqlite3
    import hashlib
    data = tmp_path/'data'
    data.mkdir()
    database = data/'history.sqlite3'
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE hands (value TEXT)')
        connection.execute('INSERT INTO hands VALUES (?)', ('原始牌局',))
    original = database.read_bytes()
    (data/'control_settings.json').write_text('{"value":1}')
    for name in ('profiles','ranges'):
        (data/name).mkdir()
        (data/name/'user.json').write_text('{"value":2}')
    (data/'秘密.txt').write_text('不應複製', encoding='utf-8')
    backup = snapshot_user_data(data, '1.0.0', '1.1.0')
    assert database.read_bytes() == original
    with sqlite3.connect(backup/'history.sqlite3') as connection:
        assert connection.execute('SELECT value FROM hands').fetchone()[0] == '原始牌局'
    assert (backup/'control_settings.json').read_text() == '{"value":1}'
    assert (backup/'profiles'/'user.json').is_file()
    assert (backup/'ranges'/'user.json').is_file()
    assert not (backup/'秘密.txt').exists()
    assert (backup/'snapshot.json').is_file()


def test_snapshot_bad_database_blocks_version_switch(tmp_path):
    client, release, payload = make_cached_client(tmp_path)
    atomic_json(tmp_path/'current.json', {'version':'1.0.0','previous':None,'pending':False})
    client.user_data.mkdir()
    (client.user_data/'history.sqlite3').write_bytes(b'not-a-database')
    with zipfile.ZipFile(tmp_path/'app.zip', 'w') as z:
        z.writestr('PokerLens.exe', b'x')
    payload = (tmp_path/'app.zip').read_bytes()
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    client.product['update_public_key'] = public
    body = json.dumps({'schema':1,'app_id':'PokerLens','version':'1.1.0','url':'https://github.com/a/b/releases/download/v1.1.0/app.zip','sha256':__import__('hashlib').sha256(payload).hexdigest(),'size':len(payload)}).encode()
    release = verify_manifest(body,base64.b64encode(key.sign(body)),public,'PokerLens')
    with pytest.raises(UpdateError, match='備份'):
        client.install(release,tmp_path)
    assert load_state(tmp_path)['version'] == '1.0.0'
    assert not (tmp_path/'versions'/'1.1.0').exists()
    assert (client.user_data/'history.sqlite3').read_bytes() == b'not-a-database'

def test_snapshot_never_follows_linked_profile(tmp_path, monkeypatch):
    from updates import backup
    data = tmp_path/'data'
    (data/'profiles').mkdir(parents=True)
    profile = data/'profiles'/'linked.json'
    profile.write_text('{"private":true}')
    original = backup._is_link
    monkeypatch.setattr(backup, '_is_link', lambda path:True if path == profile else original(path))
    destination = backup.snapshot_user_data(data, '1.0.0', '1.1.0')
    assert not (destination/'profiles'/'linked.json').exists()
    assert profile.read_text() == '{"private":true}'
