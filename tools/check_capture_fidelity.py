"""Compare real loopback audio with the public Arabic fixture."""
import queue
import threading
import time
import winsound
import numpy as np
import soundfile as sf
from caption_app.config import ROOT
from caption_app.audio import Capture, devices
from caption_app.engine import ASR

a = ASR(print)
q = queue.Queue()
c = Capture(next(d[0] for d in devices() if d[2]), q.put, print, lambda _: None)
c.start()
time.sleep(.7)
threading.Thread(target=lambda: winsound.PlaySound(str(ROOT / 'tests/fixtures/arabic.wav'), winsound.SND_FILENAME)).start()
u = q.get(timeout=20)
blocks = list(u.samples(threading.Event()))
c.close()
sf.write(ROOT / 'logs/captured-arabic.wav', np.concatenate(blocks), 16000)
print('CAPTURED', a.transcribe(iter(blocks)), flush=True)
