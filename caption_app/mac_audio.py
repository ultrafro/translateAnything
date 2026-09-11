"""CoreAudio input via PortAudio. BlackHole supplies system audio on macOS."""
import threading
import sounddevice as sd

paFloat32, paComplete, paContinue = 1, 1, 0


def devices():
    found = [(i, d['name'], True) for i, d in enumerate(sd.query_devices())
             if d['max_input_channels'] > 0 and 'blackhole' in d['name'].lower()]
    return found + [(-1, 'Microphone only (no system audio)', not found)]


def microphones():
    return [(i, d['name'], i == sd.default.device[0])
            for i, d in enumerate(sd.query_devices())
            if d['max_input_channels'] > 0 and 'blackhole' not in d['name'].lower()]


class SilentStream:
    """Keep the common two-source mixer clocked in microphone-only mode."""
    def __init__(self, callback):
        self.callback = callback
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        while not self.stop.wait(.02):
            self.callback(bytes(320 * 4), 320, {}, 0)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=1)


class PyAudio:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get_device_info_by_index(self, index):
        if index == -1:
            return {'defaultSampleRate': 16000, 'maxInputChannels': 1}
        d = sd.query_devices(index)
        return {'defaultSampleRate': d['default_samplerate'],
                'maxInputChannels': d['max_input_channels']}

    def open(self, *, input_device_index, channels, rate, frames_per_buffer,
             stream_callback, **kwargs):
        if input_device_index == -1:
            return SilentStream(stream_callback)

        def callback(data, frames, timing, status):
            result = stream_callback(bytes(data), frames, timing, bool(status))
            if result[1] == paComplete:
                raise sd.CallbackStop

        return sd.RawInputStream(device=input_device_index, channels=channels,
                                 samplerate=rate, blocksize=frames_per_buffer,
                                 dtype='float32', callback=callback)
