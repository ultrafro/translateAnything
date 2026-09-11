"""Build a self-contained release, including compact FP16 model weights."""
from pathlib import Path
import shutil
from caption_app.config import ROOT
from caption_app.engine import ASR, Translator


def main():
    destination = ROOT / 'dist/Translate Anything'
    destination.mkdir(parents=True, exist_ok=True)
    for folder in ('runtime', 'caption_app', 'tools', 'tests', 'model_notices'):
        shutil.copytree(ROOT / folder, destination / folder, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache', 'python.zip', 'get-pip.py'))
    for file in ('main.py', 'Start Captions.cmd', 'Start Captions.bat', 'Start with console.cmd', 'README.md',
                 'requirements.lock.txt', 'requirements-mac.lock.txt', 'pytest.ini', 'setup_portable.py',
                 'THIRD_PARTY.md', 'START HERE.md', 'Start Captions.command', 'LICENSE'):
        shutil.copy2(ROOT / file, destination / file)
    a = ASR(print)
    a.model.save_pretrained(destination / 'models/asr')
    a.processor.save_pretrained(destination / 'models/asr')
    t = Translator(print)
    t.model.save_pretrained(destination / 'models/translation')
    t.tokenizer.save_pretrained(destination / 'models/translation')
    (destination / 'logs').mkdir(exist_ok=True)
    print(f'Release ready: {destination}', flush=True)


if __name__ == '__main__': main()
