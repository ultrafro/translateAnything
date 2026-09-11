"""Real model + real Windows playback/capture + Qt rendering integration check."""
import json
import queue
import threading
import time
import winsound
import numpy as np
import soundfile as sf
import soxr
from caption_app.config import ROOT
from caption_app.audio import Capture, devices, BLOCK
from caption_app.engine import ASR, Translator


def main():
    report = {}
    a = ASR(print)
    t = Translator(print)
    report['device'] = a.device
    audio, rate = sf.read(ROOT / 'tests/fixtures/english.wav', dtype='float32')
    audio = soxr.resample(audio, rate, 16000)
    audio = np.concatenate((audio, np.zeros(16000, np.float32)))
    updates = []
    start = time.monotonic()
    text, language = a.transcribe((audio[i:i + BLOCK] for i in range(0, len(audio), BLOCK)),
                                  lambda text: updates.append((time.monotonic() - start, text)))
    report['file'] = {'text': text, 'language': language, 'seconds': time.monotonic() - start,
                      'audio_seconds': len(audio) / 16000, 'partial_count': len(updates)}
    print('FILE', report['file'], flush=True)
    assert 'caption' in text.lower() and language == 'en', report['file']
    assert len(updates) > 3
    translations = t.translate(text, language, ['en', 'ar'])
    report['translations'] = translations
    assert translations['en'] == text and any('\u0600' <= c <= '\u06ff' for c in translations['ar'])
    back = t.translate('مرحباً. كيف حالك اليوم؟', 'ar', ['en', 'ar'])
    report['arabic_to_english'] = back
    assert 'you' in back['en'].lower()

    arabic, arabic_rate = sf.read(ROOT / 'tests/fixtures/arabic.wav', dtype='float32')
    if arabic.ndim == 2: arabic = arabic.mean(axis=1)
    arabic = np.concatenate((soxr.resample(arabic, arabic_rate, 16000), np.zeros(16000, np.float32)))
    ar_text, ar_lang = a.transcribe((arabic[i:i + BLOCK] for i in range(0, len(arabic), BLOCK)))
    report['arabic_asr'] = {'text': ar_text, 'language': ar_lang, 'translation': t.translate(ar_text, ar_lang, ['en', 'ar'])}
    print('ARABIC', report['arabic_asr'], flush=True)
    assert ar_lang == 'ar' and 'الأطلسي' in ar_text

    utterances = queue.Queue()
    device = next(d[0] for d in devices() if d[2])
    statuses = []
    capture = Capture(device, utterances.put, lambda msg: (statuses.append(msg), print(msg)), lambda _: None)
    capture.start()
    time.sleep(1)
    playback = threading.Thread(target=lambda: winsound.PlaySound(str(ROOT / 'tests/fixtures/english.wav'), winsound.SND_FILENAME))
    playback.start()
    stop = threading.Event()
    live_results = []
    deadline = time.monotonic() + 35
    try:
        while time.monotonic() < deadline:
            try:
                utterance = utterances.get(timeout=1)
            except queue.Empty:
                if not playback.is_alive() and live_results: break
                continue
            partials = []
            started = time.monotonic()
            live_text, lang = a.transcribe(utterance.samples(stop), lambda x: partials.append((time.monotonic() - started, x)))
            print('LIVE', live_text, lang, flush=True)
            live_translation = t.translate(live_text, lang, ['en', 'ar']) if live_text else {}
            live_results.append({'text': live_text, 'language': lang, 'translations': live_translation,
                                 'first_partial_seconds': partials[0][0] if partials else None})
    finally:
        capture.close()
        playback.join(timeout=15)
    assert 'caption' in ' '.join(x['text'] for x in live_results).lower(), live_results
    report['loopback'] = live_results
    report['capture_status'] = statuses

    from PySide6.QtWidgets import QApplication
    from caption_app.ui import Window
    app = QApplication([])
    w = Window(load_models=False)
    w.show()
    w.overlay.display(text, translations)
    app.processEvents()
    w.overlay.place()
    app.processEvents()
    screen = app.primaryScreen().availableGeometry()
    rect = w.overlay.geometry()
    assert rect.left() == screen.left() + 20
    assert rect.bottom() < screen.bottom() and rect.bottom() > screen.bottom() - 100
    assert 'English' in w.overlay.transcript.toPlainText() and 'Arabic' in w.overlay.transcript.toPlainText()
    (ROOT / 'logs').mkdir(exist_ok=True)
    w.grab().save(str(ROOT / 'logs/settings.png'))
    w.overlay.grab().save(str(ROOT / 'logs/overlay.png'))
    report['overlay'] = {'languages': 2, 'position': 'bottom left', 'geometry': [rect.x(), rect.y(), rect.width(), rect.height()]}
    w.close()
    (ROOT / 'logs/end_to_end.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), 'utf-8')
    print('END TO END PASSED', flush=True)


if __name__ == '__main__':
    main()
