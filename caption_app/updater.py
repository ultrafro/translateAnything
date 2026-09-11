"""Download releases in the background; transactional source updates at next launch.

Only application files are updated. Models, settings, logs and portable Python
are never archive targets. A changed dependency contract requires a fresh install.
"""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import urllib.request
import zipfile
from contextlib import contextmanager
from .version import VERSION, UPDATE_API

REPOSITORY = 'ultrafro/translateAnything'
API = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
MAX_BYTES = 16 * 1024 * 1024
FILES = {'main.py', 'README.md', 'START HERE.md', 'THIRD_PARTY.md', 'LICENSE'}


def version(value):
    if not re.fullmatch(r'v?\d+\.\d+\.\d+', value):
        raise ValueError('Unsupported release version')
    return tuple(map(int, value.lstrip('v').split('.')))


def allowed(name):
    p = PurePosixPath(name)
    return ('\\' not in name and not p.is_absolute() and '..' not in p.parts
            and str(p) == name and (name in FILES or
            (len(p.parts) == 2 and p.parts[0] == 'caption_app' and p.suffix == '.py')))


def fetch(url):
    if not url.startswith('https://'):
        raise ValueError('Updates require HTTPS')
    request = urllib.request.Request(url, headers={'User-Agent': 'TranslateAnything/' + VERSION,
                                                  'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('Update is too large')
    return data


def unpack(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or sum(i.file_size for i in z.infolist()) > MAX_BYTES:
            raise ValueError('Invalid update archive')
        if 'update.json' not in names or any(n != 'update.json' and not allowed(n) for n in names):
            raise ValueError('Unsafe update path')
        manifest = json.loads(z.read('update.json'))
        version(manifest['version'])
        if manifest['api'] != UPDATE_API:
            raise ValueError('This release needs a new portable download')
        if set(manifest['files']) != set(names) - {'update.json'}:
            raise ValueError('Incomplete update manifest')
        files = {n: z.read(n) for n in manifest['files']}
        if not {'main.py', 'caption_app/version.py', 'caption_app/updater.py'} <= files.keys():
            raise ValueError('Incomplete application update')
        for name, content in files.items():
            if hashlib.sha256(content).hexdigest() != manifest['files'][name]:
                raise ValueError('Update checksum mismatch')
        return manifest, files


@contextmanager
def update_lock(root, name='lock'):
    """OS lock releases even after a crash. No stale lock-file guessing."""
    folder = root / '.updates'
    folder.mkdir(exist_ok=True)
    with (folder / name).open('a+b') as handle:
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            if handle.read(1) == b'':
                handle.write(b'0'); handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield folder
        finally:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def check(root, report=print):
    try:
        with update_lock(root) as folder:
            release = json.loads(fetch(API))
            if release.get('draft') or release.get('prerelease'):
                return
            if version(release['tag_name']) <= version(VERSION):
                report(f'Version {VERSION} • up to date')
                return
            asset = next(a for a in release['assets'] if a['name'] == 'app-update.zip')
            url = asset['browser_download_url']
            if not url.startswith(f'https://github.com/{REPOSITORY}/releases/download/'):
                raise ValueError('Unexpected update source')
            digest = asset.get('digest', '')
            if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
                raise ValueError('Release is missing its SHA-256 digest')
            data = fetch(url)
            if hashlib.sha256(data).hexdigest() != digest[7:]:
                raise ValueError('Download checksum mismatch')
            manifest, _ = unpack(data)
            if version(manifest['version']) != version(release['tag_name']):
                raise ValueError('Release version mismatch')
            temp = folder / 'download.tmp'
            temp.write_bytes(data)
            temp.replace(folder / 'pending.zip')
            report(f"Update {manifest['version']} downloaded • installs next time you open the app")
    except Exception as exc:
        report(f'Update check unavailable: {exc}. Captions still work.')


def restore(root, folder):
    journal = folder / 'journal.json'
    if not journal.exists():
        return
    entries = json.loads(journal.read_text('utf-8'))
    for name, existed in entries.items():
        if not allowed(name):
            raise ValueError('Unsafe recovery path')
        target = root / name
        if existed:
            shutil.copy2(folder / 'backup' / name, target)
        else:
            target.unlink(missing_ok=True)
    journal.unlink()


def apply_pending(root):
    with update_lock(root) as folder:
        restore(root, folder)
        pending = folder / 'pending.zip'
        if not pending.exists():
            return False
        manifest, files = unpack(pending.read_bytes())
        if version(manifest['version']) <= version(VERSION):
            pending.unlink()
            return False
        entries = {}
        for name in files:
            target = root / name
            if target.is_symlink() or target.parent.is_symlink():
                raise ValueError('Cannot update symlinked application files')
            entries[name] = target.exists()
            if target.exists():
                backup = folder / 'backup' / name
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
        journal = folder / 'journal.json'
        journal.write_text(json.dumps(entries), 'utf-8')
        try:
            for name, content in files.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                temp = target.with_suffix('.update-tmp')
                temp.write_bytes(content)
                temp.replace(target)
            journal.unlink()
            pending.unlink()
        except Exception:
            restore(root, folder)
            raise
        return True
