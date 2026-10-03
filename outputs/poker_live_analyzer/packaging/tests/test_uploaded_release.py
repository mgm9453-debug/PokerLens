import hashlib
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('verify_uploaded_release', Path(__file__).resolve().parents[2]/'scripts/verify_uploaded_release.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize('problem', [None, 'digest', 'size', 'state', 'draft', 'missing', 'duplicate'])
def test_uploaded_release_must_match(tmp_path, problem):
    (tmp_path/'manifest.json').write_bytes(b'content')
    asset = {'name': 'manifest.json', 'state': 'uploaded', 'size': 7,
             'digest': 'sha256:'+hashlib.sha256(b'content').hexdigest()}
    release = {'tag_name': 'v1.0.2', 'draft': True, 'assets': [asset]}
    if problem in ('digest', 'size', 'state'):
        asset[problem] = None
    elif problem == 'draft':
        release['draft'] = False
    elif problem == 'missing':
        release['assets'] = []
    elif problem == 'duplicate':
        release['assets'].append(asset.copy())
    if problem:
        with pytest.raises(ValueError):
            module.verify_uploaded(tmp_path, release, 'v1.0.2')
    else:
        module.verify_uploaded(tmp_path, release, 'v1.0.2')
