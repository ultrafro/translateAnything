"""Exercise the shipped GUI, workers, playback capture, translations, and restart."""
import os
os.environ['HF_HUB_OFFLINE'] = '1'
import json
import threading
import time
import winsound
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from caption_app.config import ROOT
from caption_app.ui import Window


def main():
    app = QApplication([])
    window = Window()
    window.show()
    records, statuses = [], []
    window.events.caption.connect(lambda ident, text, translations, final:
        records.append({'time': time.monotonic(), 'id': ident, 'text': text,
                        'translations': translations, 'final': final}))
    window.events.status.connect(statuses.append)
    state = {'phase': 'loading', 'start': time.monotonic(), 'ok': False}

    def playback(name):
        state['playback_done'] = False
        def play():
            winsound.PlaySound(str(ROOT / 'tests/fixtures' / name), winsound.SND_FILENAME)
            state['playback_done'] = True
            state['playback_end'] = time.monotonic()
        threading.Thread(target=play, daemon=True).start()

    def tick():
        try:
            elapsed = time.monotonic() - state['start']
            assert elapsed < 100, (state, statuses[-5:])
            if state['phase'] == 'loading' and window.loaded:
                window.start.click()
                state.update(phase='english', speech_start=time.monotonic())
                QTimer.singleShot(700, lambda: playback('english.wav'))
            elif state['phase'] == 'english':
                translated = [r for r in records if r['final'] and 'ar' in r['translations'] and 'arabic' in r['text'].lower()]
                if translated and state.get('playback_done') and time.monotonic() - state['playback_end'] > 2:
                    state['english_first_translation_seconds'] = next(r['time'] for r in records if r['translations']) - state['speech_start']
                    window.start.click()
                    assert not window.active and window.overlay.isVisible()
                    state['retained_after_stop'] = len(window.overlay.history)
                    window.start.click()
                    state.update(phase='arabic', arabic_session=window.engine.session)
                    QTimer.singleShot(700, lambda: playback('arabic.wav'))
            elif state['phase'] == 'arabic':
                translated = [r for r in records if r['final'] and r['id'][0] == state['arabic_session']
                              and 'en' in r['translations'] and 'الأطلسي' in r['text']]
                if (translated and state.get('playback_done') and time.monotonic() - state['playback_end'] > 2
                        and any('جيري' in r['text'] and r['text'].startswith('تشكلت')
                                and 'storm' in r['translations']['en'].lower() for r in translated)):
                    window.grab().save(str(ROOT / 'logs/live-app.png'))
                    window.overlay.grab().save(str(ROOT / 'logs/live-arabic-overlay.png'))
                    assert window.overlay.isVisible()
                    rect = window.overlay.geometry()
                    screen = window.overlay.screen().availableGeometry()
                    assert rect.left() == screen.left() + 20
                    assert len(window.overlay.history) >= 2
                    assert 'English and Arabic' in window.overlay.transcript.toPlainText()
                    assert 25 < screen.bottom() - rect.bottom() < 60
                    assert not any('error:' in s.lower() or 'failed:' in s.lower() for s in statuses), statuses
                    state['ok'] = True
                    state['phase'] = 'passed'
                    window.start.click()
                    window.close()
                    app.quit()
        except Exception as exc:
            state['error'] = repr(exc)
            window.close()
            app.quit()

    timer = QTimer(); timer.timeout.connect(tick); timer.start(100)
    app.exec()
    (ROOT / 'logs/live-app-test.json').write_text(json.dumps({'state': state, 'statuses': statuses, 'captions': records},
                                                           indent=2, ensure_ascii=False), 'utf-8')
    print(json.dumps(state), flush=True)
    assert state['ok'], state


if __name__ == '__main__': main()
