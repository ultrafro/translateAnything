"""WASAPI loopback and bounded, silence-delimited live audio streams."""
import queue
import sys
import threading
import time
from contextlib import ExitStack
from collections import deque
import numpy as np

RATE = 16000
BLOCK = 320
MIC_SPEECH_THRESHOLD = .0006


def audio_backend():
    if sys.platform == 'darwin':
        from . import mac_audio
        return mac_audio
    import pyaudiowpatch
    return pyaudiowpatch


def input_mono(raw, channels, microphone=False):
    frames = np.frombuffer(raw, np.float32).reshape(-1, channels)
    if microphone and channels > 1:
        # Some microphone arrays expose opposite-phase channels. Averaging them
        # can cancel the voice while the device still reports an input signal.
        strongest = int(np.argmax(np.mean(frames * frames, axis=0)))
        return frames[:, strongest].copy()
    return frames.mean(axis=1)


class Utterance:
    def __init__(self):
        self.blocks = queue.Queue(maxsize=800)
        self.ended = threading.Event()

    def put(self, block):
        self.blocks.put_nowait(block)

    def finish(self):
        self.ended.set()

    def samples(self, stop):
        while not stop.is_set():
            try:
                yield self.blocks.get(timeout=.1)
            except queue.Empty:
                if self.ended.is_set():
                    return


class Segmenter:
    def __init__(self, deliver, threshold=.008):
        self.deliver = deliver
        self.threshold = threshold
        self.pre = deque(maxlen=10)
        self.current = None
        self.quiet = self.length = 0

    def feed(self, block):
        speech = float(np.sqrt(np.mean(block * block))) > self.threshold
        if self.current is None:
            self.pre.append(block)
            if not speech:
                return
            self.current = Utterance()
            for previous in self.pre:
                self.current.put(previous)
            self.pre.clear()
            self.deliver(self.current)
            self.length = self.quiet = 0
        else:
            self.current.put(block)
        self.length += 1
        self.quiet = 0 if speech else self.quiet + 1
        if self.quiet >= 35 or self.length >= 600:
            self.current.finish()
            self.current = None

    def finish(self):
        if self.current:
            self.current.finish()
            self.current = None


def devices():
    pa = audio_backend()
    if sys.platform == 'darwin':
        return pa.devices()
    with pa.PyAudio() as p:
        default = p.get_default_wasapi_loopback()
        return [(int(d['index']), d['name'], int(d['index']) == int(default['index']))
                for d in p.get_loopback_device_info_generator()]


def microphones():
    pa = audio_backend()
    if sys.platform == 'darwin':
        return pa.microphones()
    with pa.PyAudio() as p:
        host = p.get_host_api_info_by_type(pa.paWASAPI)
        default = int(host['defaultInputDevice'])
        return [(int(d['index']), d['name'], int(d['index']) == default)
                for d in (p.get_device_info_by_index(i) for i in range(p.get_device_count()))
                if d['hostApi'] == host['index'] and d['maxInputChannels'] > 0 and not d.get('isLoopbackDevice')]


class FrameMixer:
    """Mix bounded 20 ms queues; a silent output never holds up the microphone."""
    def __init__(self, sources):
        self.frames = [deque(maxlen=10) for _ in range(sources)]

    def put(self, source, block):
        self.frames[source].append(block)

    def read(self):
        mixed = np.zeros(BLOCK, np.float32)
        for frames in self.frames:
            if frames:
                mixed += frames.popleft()
        return np.clip(mixed, -1, 1)


class Capture:
    def __init__(self, device, deliver, status, level, threshold=.008, microphone=None,
                 mic_level=None, microphone_gain=2.0):
        self.device, self.deliver = device, deliver
        self.status, self.level = status, level
        self.microphone = microphone
        self.mic_level = mic_level or (lambda _: None)
        self.microphone_gain = microphone_gain
        self.stop = threading.Event()
        def speech_started(utterance):
            self.status('Speech detected • sending audio to recognition')
            deliver(utterance)
        self.segmenter = Segmenter(speech_started, min(threshold, MIC_SPEECH_THRESHOLD) if microphone is not None else threshold)
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def run(self):
        import soxr
        try:
            pa = audio_backend()
            with pa.PyAudio() as p, ExitStack() as stack:
                indices = [self.device] + ([self.microphone] if self.microphone is not None else [])
                states = []
                packets = queue.Queue(maxsize=200)
                overflow = threading.Event()
                for source, index in enumerate(indices):
                    d = p.get_device_info_by_index(index)
                    rate, channels = int(d['defaultSampleRate']), int(d['maxInputChannels'])
                    states.append([channels, soxr.ResampleStream(rate, RATE, 1, dtype='float32'),
                                   np.empty(0, dtype=np.float32)])

                    def callback(data, frame_count, time_info, flags, source=source):
                        if flags:
                            overflow.set()
                        try:
                            packets.put_nowait((source, data))
                        except queue.Full:
                            overflow.set()
                        return (None, pa.paComplete if self.stop.is_set() else pa.paContinue)

                    stack.enter_context(p.open(format=pa.paFloat32, channels=channels, rate=rate,
                                        input=True, input_device_index=index,
                                        frames_per_buffer=rate // 50, stream_callback=callback))
                mixer = FrameMixer(len(indices))
                next_tick = time.monotonic() + .06
                self.status('Listening to system audio' + (' + microphone' if self.microphone is not None else '')
                            + ' • audio stays on this computer')
                while not self.stop.is_set():
                    if overflow.is_set():
                        raise RuntimeError('Audio input overflow; restart capture')
                    try:
                        source, raw = packets.get(timeout=max(0, next_tick - time.monotonic()))
                        channels, resampler, pending = states[source]
                        mono = input_mono(raw, channels, microphone=source == 1)
                        if source == 1:
                            mono = np.clip(mono * self.microphone_gain, -1, 1)
                            rms = float(np.sqrt(np.mean(mono * mono)))
                            self.mic_level(max(0, min(100, int((20 * np.log10(max(rms, 1e-8)) + 80) * 1.25))))
                        pending = np.concatenate((pending, resampler.resample_chunk(mono)))
                        while len(pending) >= BLOCK:
                            block = pending[:BLOCK].copy()
                            if len(indices) == 1:
                                self.segmenter.feed(block)
                                self.level(min(100, int(np.sqrt(np.mean(block * block)) * 500)))
                            else:
                                mixer.put(source, block)
                            pending = pending[BLOCK:]
                        states[source][2] = pending
                    except queue.Empty:
                        pass
                    now = time.monotonic()
                    if now >= next_tick:
                        if len(indices) > 1:
                            block = mixer.read()
                            self.level(min(100, int(np.sqrt(np.mean(block * block)) * 500)))
                            self.segmenter.feed(block)
                        next_tick = max(next_tick + .02, now - .04)
        except Exception as exc:
            self.status(f'Audio capture stopped: {exc}. Select an active output device and restart.')
        finally:
            self.segmenter.finish()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3)
