"""Real ASR/translation from quiet simulated mic packets through the capture path.

Only the device driver is simulated. No sound is played and no user audio is recorded.
"""
import json
import queue
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import soundfile as sf
import soxr
from caption_app.config import ROOT
from caption_app.audio import Capture
from caption_app.engine import ASR, Translator

asr = ASR(print)
translator = Translator(print)
voice, rate = sf.read(ROOT / 'tests/fixtures/english.wav', dtype='float32')
voice = soxr.resample(voice, rate, 48000)
voice = voice * (.001 / max(np.sqrt(np.mean(voice * voice)), 1e-8))
voice = np.concatenate((voice, np.zeros(48000, np.float32)))
stereo = np.column_stack((voice, -voice)).astype(np.float32)
stop = threading.Event()

class Stream:
    def __init__(self, callback, index):
        self.callback, self.index = callback, index
        self.thread = threading.Thread(target=self.run)
    def run(self):
        for i in range(0, len(stereo), 960):
            if stop.is_set(): break
            packet = stereo[i:i+960] if self.index == 1 else np.zeros((960, 2), np.float32)
            self.callback(packet.tobytes(), len(packet), {}, 0)
            time.sleep(.02)
    def __enter__(self): self.thread.start(); return self
    def __exit__(self, *args): stop.set(); self.thread.join()

class Audio:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def get_device_info_by_index(self, index): return {'defaultSampleRate': 48000, 'maxInputChannels': 2}
    def open(self, **kwargs): return Stream(kwargs['stream_callback'], kwargs['input_device_index'])

utterances, levels, statuses = queue.Queue(), [], []
results, partials = [], []
with patch.dict(sys.modules, {'pyaudiowpatch': SimpleNamespace(PyAudio=Audio, paFloat32=1, paComplete=1, paContinue=0)}):
    capture = Capture(0, utterances.put, statuses.append, lambda _: None, microphone=1, mic_level=levels.append)
    capture.start()
    deadline = time.monotonic() + 20
    try:
        while time.monotonic() < deadline:
            try: u = utterances.get(timeout=1)
            except queue.Empty:
                if results: break
                continue
            text, language = asr.transcribe(u.samples(stop), partials.append, listening_languages=['en', 'vi'])
            if text:
                results.append({'text': text, 'source': language,
                                'translations': translator.translate(text, language, ['en', 'vi'])})
    finally:
        capture.close()
assert not any('stopped:' in message for message in statuses), statuses
assert partials, 'No live recognition updates from the microphone path'
assert 'caption' in ' '.join(r['text'] for r in results).lower(), results
assert all(r['source'] == 'en' and r['translations'].get('vi') for r in results), results
report = {'passed': True, 'input': 'quiet opposite-phase stereo mic; silent system audio',
          'partial_updates': len(partials), 'meter_peak': max(levels), 'results': results}
(ROOT / 'logs/quiet-microphone-test.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), 'utf-8')
print('QUIET MICROPHONE THROUGH ASR AND TRANSLATION PASSED', flush=True)
