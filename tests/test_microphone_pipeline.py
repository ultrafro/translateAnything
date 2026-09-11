"""Exercise the actual capture/resampling/mixing/segmentation path with quiet speech."""
import sys
import threading
import time
from types import SimpleNamespace
import numpy as np
from caption_app.audio import Capture, BLOCK, input_mono


def test_microphone_array_channels_do_not_cancel_voice():
    voice = np.sin(np.arange(960) * .1).astype(np.float32) * .02
    raw = np.column_stack((voice, -voice)).astype(np.float32).tobytes()
    assert np.max(abs(input_mono(raw, 2, microphone=True))) > .019
    assert np.max(abs(input_mono(raw, 2))) == 0


def test_quiet_mic_reaches_recognizer_with_silent_system_audio(monkeypatch):
    from caption_app import audio
    utterances, levels, statuses = [], [], []
    # Speech-like harmonics below the old .004 RMS gate; this already moves the mic meter.
    n = np.arange(48000)
    voice = (.0015 * np.sin(2 * np.pi * 180 * n / 48000)).astype(np.float32)
    stereo = np.column_stack((voice, -voice)).astype(np.float32)
    stopped = threading.Event()

    class Stream:
        def __init__(self, callback, index):
            self.callback, self.index = callback, index
            self.thread = threading.Thread(target=self.send)
        def send(self):
            for i in range(100):
                if stopped.is_set(): break
                packet = stereo[i * 960:(i + 1) * 960] if self.index == 1 and i < 50 else np.zeros((960, 2), np.float32)
                self.callback(packet.tobytes(), 960, {}, 0)
                time.sleep(.02)
        def __enter__(self):
            self.thread.start()
            return self
        def __exit__(self, *args):
            stopped.set()
            self.thread.join()
    class Audio:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get_device_info_by_index(self, index):
            return {'defaultSampleRate': 48000, 'maxInputChannels': 2}
        def open(self, **kwargs): return Stream(kwargs['stream_callback'], kwargs['input_device_index'])
    monkeypatch.setitem(sys.modules, 'pyaudiowpatch', SimpleNamespace(PyAudio=Audio, paFloat32=1, paComplete=1, paContinue=0))
    monkeypatch.setattr(audio, 'audio_backend', lambda: sys.modules['pyaudiowpatch'])
    capture = Capture(0, utterances.append, statuses.append, lambda _: None,
                      microphone=1, mic_level=levels.append)
    capture.start()
    time.sleep(2.3)
    capture.close()
    assert not capture.thread.is_alive()
    assert not any('stopped:' in message for message in statuses)
    assert max(levels) > 0
    assert utterances, 'Meter moves but speech never reaches ASR'
    samples = np.concatenate([block for u in utterances for block in u.samples(threading.Event())])
    assert len(samples) > BLOCK * 30
    assert np.sqrt(np.mean(samples * samples)) > .0006
