"""Mac CI: actual bundled Python, synthetic speech, streaming ASR and translation."""
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import soundfile as sf
import soxr
from caption_app.engine import ASR, Translator


def main():
    if sys.platform != 'darwin':
        raise SystemExit('Run this check on macOS.')
    fixture = Path('logs/mac-speech.aiff')
    fixture.parent.mkdir(exist_ok=True)
    subprocess.run(['say', '-o', str(fixture), 'Hello, this is a test of live captions.'], check=True)
    audio, rate = sf.read(fixture, dtype='float32')
    if audio.ndim > 1: audio = audio.mean(axis=1)
    audio = np.concatenate((soxr.resample(audio, rate, 16000), np.zeros(16000, np.float32)))
    asr = ASR(print)
    partials = []
    start = time.monotonic()
    text, source = asr.transcribe((audio[i:i+320] for i in range(0, len(audio), 320)),
                                  partials.append, listening_languages=['en', 'ar'])
    print('Recognized:', text, 'seconds:', round(time.monotonic() - start, 2), flush=True)
    assert 'hello' in text.lower() and 'caption' in text.lower(), text
    assert partials and source == 'en'
    translator = Translator(print)
    translated = translator.translate(text, source, ['en', 'ar'])
    assert translated['en'] == text and any('\u0600' <= c <= '\u06ff' for c in translated['ar'])
    print('Translation:', translated, flush=True)


if __name__ == '__main__': main()
