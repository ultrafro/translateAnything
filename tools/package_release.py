"""Small first-install packages include Python; dependencies/models download once."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from caption_app.version import VERSION, UPDATE_API
from caption_app.updater import allowed

WIN_URL = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'
WIN_HASH = '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'
MAC_URL = 'https://github.com/astral-sh/python-build-standalone/releases/download/20260901/cpython-3.12.14%2B20260901-aarch64-apple-darwin-install_only_stripped.tar.gz'
MAC_HASH = '81a359f1cfadd4da11766534c5913791cea55f26e1bb902cacd2a531bb1e4b2b'


def download(url, digest):
    data = urllib.request.urlopen(url, timeout=90).read()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('Interpreter checksum mismatch')
    return data


def main():
    out = ROOT / 'dist/releases'
    out.mkdir(parents=True, exist_ok=True)
    source = {str(p.relative_to(ROOT)).replace('\\', '/'): p.read_bytes()
              for p in (ROOT / 'caption_app').glob('*.py')}
    for name in ['main.py', 'README.md', 'START HERE.md', 'THIRD_PARTY.md', 'LICENSE',
                 'setup_portable.py', 'requirements.lock.txt', 'requirements-mac.lock.txt',
                 'Start Captions.bat', 'Start Captions.cmd', 'Start with console.cmd', 'Start Captions.command']:
        source[name] = (ROOT / name).read_bytes()
    for p in (ROOT / 'model_notices').glob('*.md'):
        source['model_notices/' + p.name] = p.read_bytes()
    app_files = {n: data for n, data in source.items() if allowed(n)}
    manifest = {'version': VERSION, 'api': UPDATE_API,
                'files': {n: hashlib.sha256(data).hexdigest() for n, data in app_files.items()}}
    with zipfile.ZipFile(out / 'app-update.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('update.json', json.dumps(manifest))
        for name, data in app_files.items(): z.writestr(name, data)
    if '--update-only' in sys.argv:
        return
    prefix = 'Translate Anything/'
    with zipfile.ZipFile(out / 'Translate-Anything-Windows.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in source.items(): z.writestr(prefix + name, data)
        with zipfile.ZipFile(io.BytesIO(download(WIN_URL, WIN_HASH))) as runtime:
            for name in runtime.namelist():
                data = runtime.read(name)
                if name == 'python312._pth':
                    data = b'python312.zip\n.\nLib/site-packages\n..\nimport site\n'
                z.writestr(prefix + 'runtime/' + name, data)
    with tarfile.open(out / 'Translate-Anything-Mac-Apple-Silicon.tar.gz', 'w:gz') as tar:
        for name, data in source.items():
            info = tarfile.TarInfo(prefix + name)
            info.size = len(data)
            info.mode = 0o755 if name.endswith('.command') else 0o644
            tar.addfile(info, io.BytesIO(data))
        with tarfile.open(fileobj=io.BytesIO(download(MAC_URL, MAC_HASH)), mode='r:gz') as runtime:
            for member in runtime:
                if not member.name.startswith('python/'):
                    continue
                contents = runtime.extractfile(member) if member.isfile() else None
                member.name = prefix + 'runtime/' + member.name[len('python/'):]
                if member.issym() and member.linkname.startswith('python/'):
                    member.linkname = prefix + 'runtime/' + member.linkname[len('python/'):]
                tar.addfile(member, contents)
    checksums = '\n'.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name
                          for p in sorted(out.iterdir()) if p.suffix in {'.zip', '.gz'})
    (out / 'SHA256SUMS.txt').write_text(checksums + '\n')
    print('Release packages ready:', out)


if __name__ == '__main__': main()
