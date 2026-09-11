import hashlib
import io
import json
import zipfile
import pytest
from caption_app import updater as u


@pytest.fixture(autouse=True)
def installed_version(monkeypatch):
    monkeypatch.setattr(u, 'VERSION', '1.0.0')


def bundle(extra=None, release='1.0.1'):
    files = {'main.py': b'# new main', 'caption_app/version.py': b"VERSION = '1.0.1'",
             'caption_app/updater.py': b'# updater'}
    files.update(extra or {})
    manifest = {'version': release, 'api': 1,
                'files': {n: hashlib.sha256(v).hexdigest() for n, v in files.items()}}
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as z:
        z.writestr('update.json', json.dumps(manifest))
        for n, v in files.items(): z.writestr(n, v)
    return output.getvalue()


def test_download_apply_preserves_user_data(tmp_path, monkeypatch):
    data = bundle()
    release = {'tag_name': 'v1.0.1', 'assets': [{'name': 'app-update.zip',
        'browser_download_url': f'https://github.com/{u.REPOSITORY}/releases/download/v1.0.1/app-update.zip',
        'digest': 'sha256:' + hashlib.sha256(data).hexdigest()}]}
    monkeypatch.setattr(u, 'fetch', lambda url: json.dumps(release).encode() if url == u.API else data)
    (tmp_path / 'main.py').write_text('old')
    (tmp_path / 'settings.json').write_text('private')
    (tmp_path / 'models').mkdir()
    (tmp_path / 'models/weights').write_bytes(b'model')
    messages = []
    u.check(tmp_path, messages.append)
    assert 'downloaded' in messages[-1]
    assert (tmp_path / 'main.py').read_text() == 'old'
    assert u.apply_pending(tmp_path)
    assert (tmp_path / 'main.py').read_bytes() == b'# new main'
    assert (tmp_path / 'settings.json').read_text() == 'private'
    assert (tmp_path / 'models/weights').read_bytes() == b'model'
    assert not u.apply_pending(tmp_path)


@pytest.mark.parametrize('name', ['../escape.py', '/escape.py', 'caption_app/../../escape.py',
                                'settings.json', 'runtime/python.exe', 'caption_app\\evil.py'])
def test_archive_cannot_escape_application_files(name):
    with pytest.raises(ValueError): u.unpack(bundle({name: b'bad'}))


def test_invalid_checksum_is_not_staged(tmp_path, monkeypatch):
    release = {'tag_name': 'v1.0.1', 'assets': [{'name': 'app-update.zip',
        'browser_download_url': f'https://github.com/{u.REPOSITORY}/releases/download/v1.0.1/app-update.zip',
        'digest': 'sha256:' + '0' * 64}]}
    monkeypatch.setattr(u, 'fetch', lambda url: json.dumps(release).encode() if url == u.API else bundle())
    messages = []
    u.check(tmp_path, messages.append)
    assert 'checksum mismatch' in messages[-1]
    assert not (tmp_path / '.updates/pending.zip').exists()


def test_failed_install_restores_old_files(tmp_path, monkeypatch):
    folder = tmp_path / '.updates'
    folder.mkdir()
    (folder / 'pending.zip').write_bytes(bundle())
    (tmp_path / 'main.py').write_text('old main')
    from pathlib import Path
    replace = Path.replace
    def fail(self, target):
        if str(target).endswith('version.py'): raise OSError('disk error')
        return replace(self, target)
    monkeypatch.setattr(Path, 'replace', fail)
    with pytest.raises(OSError): u.apply_pending(tmp_path)
    assert (tmp_path / 'main.py').read_text() == 'old main'
    assert not (tmp_path / 'caption_app/version.py').exists()


def test_crash_recovery(tmp_path):
    folder = tmp_path / '.updates'
    (folder / 'backup').mkdir(parents=True)
    (folder / 'backup/main.py').write_text('previous')
    (folder / 'journal.json').write_text(json.dumps({'main.py': True}))
    (tmp_path / 'main.py').write_text('half installed')
    assert not u.apply_pending(tmp_path)
    assert (tmp_path / 'main.py').read_text() == 'previous'


def test_offline_check_does_not_stop_app(tmp_path, monkeypatch):
    def offline(_): raise OSError('offline')
    monkeypatch.setattr(u, 'fetch', offline)
    messages = []
    u.check(tmp_path, messages.append)
    assert 'Captions still work' in messages[-1]
