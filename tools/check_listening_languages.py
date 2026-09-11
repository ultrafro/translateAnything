"""Check real recorded English/Arabic with the selectable listening sets."""
import json
import soundfile as sf
import soxr
import numpy as np
from caption_app.config import ROOT
from caption_app.engine import ASR

a = ASR(print)
results = []
for fixture, selected, expected in [('english.wav', ['en', 'vi'], 'en'),
                                     ('arabic.wav', ['en', 'ar'], 'ar'),
                                     ('arabic.wav', ['en', 'ar', 'vi'], 'ar')]:
    audio, rate = sf.read(ROOT / 'tests/fixtures' / fixture, dtype='float32')
    audio = np.concatenate((soxr.resample(audio, rate, 16000), np.zeros(16000, np.float32)))
    text, source = a.transcribe((audio[i:i+320] for i in range(0, len(audio), 320)),
                                listening_languages=selected)
    assert source == expected and len(text) > 20, (text, source, selected)
    results.append({'fixture': fixture, 'listening': selected, 'source': source, 'text': text})
(ROOT / 'logs/listening-language-test.json').write_text(json.dumps(results, indent=2, ensure_ascii=False), 'utf-8')
print('LISTENING LANGUAGE CHECKS PASSED')
