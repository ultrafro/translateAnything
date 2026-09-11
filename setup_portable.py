"""Rebuild the portable folder using an existing Python (development/repair only)."""
import hashlib
from pathlib import Path
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / 'runtime'
PYTHON_URL = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'
PYTHON_SHA256 = '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'


def main():
    RUNTIME.mkdir(exist_ok=True)
    mac = sys.platform == 'darwin'
    executable = RUNTIME / ('bin/python3' if mac else 'python.exe')
    if mac and not executable.exists():
        raise RuntimeError('Download the Mac release, which includes portable Python.')
    if not executable.exists():
        archive = RUNTIME / 'python.zip'
        urllib.request.urlretrieve(PYTHON_URL, archive)
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == PYTHON_SHA256, 'Python archive checksum mismatch'
        with zipfile.ZipFile(archive) as z:
            z.extractall(RUNTIME)
        (RUNTIME / 'python312._pth').write_text('python312.zip\n.\nLib/site-packages\n..\nimport site\n')
    pip = RUNTIME / 'get-pip.py'
    if subprocess.run([str(executable), '-s', '-m', 'pip', '--version'], capture_output=True).returncode:
        urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py', pip)
        subprocess.run([str(executable), '-s', str(pip)], check=True)
    # The embeddable interpreter deliberately ignores PYTHONPATH, including pip's
    # isolated build environment. langid is pure Python but ships as a source tar.
    subprocess.run([str(executable), '-s', '-m', 'pip', 'install',
                    'setuptools==78.1.0', 'wheel==0.45.1', '--no-warn-script-location'], check=True)
    requirements = ROOT / ('requirements-mac.lock.txt' if mac else 'requirements.lock.txt')
    options = [] if mac else ['--extra-index-url', 'https://download.pytorch.org/whl/cu130']
    subprocess.run([str(executable), '-s', '-m', 'pip', 'install', '-r', str(requirements),
                    *options, '--no-build-isolation', '--no-warn-script-location'], check=True)
    subprocess.run([str(executable), '-s', '-m', 'pip', 'check'], check=True)
    (RUNTIME / '.ready').write_text('1', 'utf-8')
    print('Setup complete. Missing models download on first start.')


if __name__ == '__main__': main()
