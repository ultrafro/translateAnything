import importlib
import sys
from types import SimpleNamespace
import threading


def test_mac_devices_and_callback_adapter(monkeypatch):
    records = [{'name': 'BlackHole 2ch', 'max_input_channels': 2, 'default_samplerate': 48000},
               {'name': 'MacBook Microphone', 'max_input_channels': 1, 'default_samplerate': 48000}]
    opened = []
    fake = SimpleNamespace(query_devices=lambda i=None: records if i is None else records[i],
                           default=SimpleNamespace(device=(1, 2)),
                           RawInputStream=lambda **kw: opened.append(kw) or kw)
    monkeypatch.setitem(sys.modules, 'sounddevice', fake)
    from caption_app import mac_audio
    monkeypatch.setattr(mac_audio, 'sd', fake)
    assert mac_audio.devices()[0] == (0, 'BlackHole 2ch', True)
    assert mac_audio.microphones() == [(1, 'MacBook Microphone', True)]
    received = []
    with mac_audio.PyAudio() as p:
        assert p.get_device_info_by_index(0)['maxInputChannels'] == 2
        p.open(input_device_index=0, channels=2, rate=48000, frames_per_buffer=960,
               stream_callback=lambda *args: received.append(args) or (None, 0))
        opened[0]['callback'](b'audio', 960, {}, False)
    assert received[0][0] == b'audio'


def test_mac_mic_only_clock():
    from caption_app.mac_audio import SilentStream
    tick = threading.Event()
    with SilentStream(lambda *args: tick.set()):
        assert tick.wait(1)
