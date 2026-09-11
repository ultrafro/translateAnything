import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from caption_app import ui


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_transcript_stays_bottom_left_when_text_changes(app):
    overlay = ui.Overlay()
    for text in ['Hello', 'A much longer caption that wraps across multiple lines. ' * 5, 'Short again']:
        overlay.display(text, {'en': text, 'ar': 'مرحباً كيف حالك اليوم؟'})
        app.processEvents()
        overlay.place()
        app.processEvents()
        screen = app.primaryScreen().availableGeometry()
        rect = overlay.geometry()
        assert rect.left() == screen.left() + 20
        assert 25 < screen.bottom() - rect.bottom() < 60
        assert not overlay.windowFlags() & Qt.WindowTransparentForInput
        assert text in overlay.transcript.toPlainText()
    overlay.close()


def test_old_session_and_translation_revisions_cannot_replace_new_captions(app, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, 'ROOT', tmp_path)
    monkeypatch.setattr(ui, 'devices', lambda: [(1, 'Test output', True)])
    w = ui.Window(load_models=False)
    w.active = True
    w.engine.session = 3
    w.on_caption((3, 1, 4), 'New text', {'en': 'New text', 'ar': 'نص جديد'}, True)
    w.on_caption((3, 1, 2), 'Old text', {'en': 'Old text'}, True)
    w.on_caption((2, 9, 9), 'Previous session', {'en': 'Previous session'}, True)
    assert w.last_translations['en'] == 'New text'
    w.on_caption((3, 2, 1), 'Next utterance', {}, False)
    assert w.last_original == 'Next utterance'
    assert w.last_translations['en'] == 'New text'
    assert w.targets() == ['en', 'ar']
    w.close()


def test_transcript_keeps_history_and_updates_revisions_in_place(app):
    overlay = ui.Overlay()
    overlay.update_caption((1, 1, 1), 'Hello', {}, False)
    overlay.update_caption((1, 1, 2), 'Hello there', {'en': 'Hello there'}, True)
    overlay.update_caption((1, 2, 1), 'Second sentence', {'en': 'Second sentence'}, True)
    overlay.render()
    assert len(overlay.history) == 2
    assert 'Hello there' in overlay.transcript.toPlainText()
    assert 'Second sentence' in overlay.transcript.toPlainText()
    for i in range(3, 55):
        overlay.update_caption((1, i, 1), f'Sentence {i}', {'en': f'Sentence {i}'}, True)
    overlay.render()
    app.processEvents()
    assert len(overlay.history) == 50
    bar = overlay.transcript.verticalScrollBar()
    assert bar.maximum() > 0
    from PySide6.QtTest import QTest
    QTest.qWait(450)
    bar.setValue(0)
    overlay.update_caption((1, 54, 2), 'Updated last sentence', {'en': 'Updated last sentence'}, True)
    overlay.render()
    assert bar.value() == 0 and not overlay.follow_live
    bar.setValue(bar.maximum())
    overlay.update_caption((1, 55, 1), 'Following again', {'en': 'Following again'}, True)
    overlay.render()
    app.processEvents()
    from PySide6.QtTest import QTest
    QTest.qWait(450)
    assert bar.value() == bar.maximum() and overlay.follow_live
    assert overlay.isVisible()
    overlay.clear_history()
    assert not overlay.history
    overlay.close()


def test_follow_scroll_is_gradual_and_user_can_pause_and_resume(app):
    from PySide6.QtTest import QTest
    overlay = ui.Overlay()
    for i in range(10):
        overlay.update_caption((1, i, 1), 'Some spoken words. ' * 8, {}, False)
    overlay.render()
    app.processEvents()
    bar = overlay.transcript.verticalScrollBar()
    overlay.resume_live()
    QTest.qWait(450)
    previous = bar.value()
    overlay.update_caption((1, 10, 1), 'Another sentence. ' * 12, {}, False)
    overlay.render()
    assert bar.value() == previous < bar.maximum()
    QTest.qWait(35)
    assert previous < bar.value() < bar.maximum()
    assert overlay.follow_live
    bar.setValue(bar.value() - 100)
    paused = bar.value()
    assert overlay.follow_button.text() == '↓ Resume live'
    QTest.qWait(100)
    assert bar.value() == paused
    overlay.follow_button.click()
    QTest.qWait(450)
    assert bar.value() == bar.maximum()
    assert overlay.follow_button.text() == '● Following live'
    overlay.close()


def test_paused_entry_stays_put_during_reflow_and_history_eviction(app):
    overlay = ui.Overlay()
    for i in range(50):
        overlay.update_caption((1, i, 1), f'Entry {i}. ' * 8, {}, False)
    overlay.render()
    app.processEvents()
    bar = overlay.transcript.verticalScrollBar()
    anchor = 'entry_1_20'
    bar.setValue(round(overlay.entry_positions()[anchor]) + 12)
    offset = overlay.entry_positions()[anchor] - bar.value()
    overlay.update_caption((1, 1, 2), 'Earlier translation gets much longer. ' * 30, {}, True)
    overlay.render()
    assert abs(overlay.entry_positions()[anchor] - bar.value() - offset) <= 1
    overlay.update_caption((1, 50, 1), 'New entry removes oldest entry', {}, False)
    overlay.render()
    assert abs(overlay.entry_positions()[anchor] - bar.value() - offset) <= 1
    assert not overlay.follow_live
    overlay.close()


def test_following_history_eviction_scrolls_instead_of_jumping(app):
    from PySide6.QtTest import QTest
    overlay = ui.Overlay()
    for i in range(50):
        overlay.update_caption((1, i, 1), f'Entry {i}. ' * 8, {}, False)
    overlay.render()
    app.processEvents()
    overlay.resume_live()
    QTest.qWait(450)
    bar = overlay.transcript.verticalScrollBar()
    positions = overlay.entry_positions()
    anchor = next(name for name, y in reversed(list(positions.items())) if y <= bar.value())
    offset = positions[anchor] - bar.value()
    overlay.update_caption((1, 50, 1), 'Next sentence. ' * 8, {}, False)
    overlay.render()
    assert abs(overlay.entry_positions()[anchor] - bar.value() - offset) <= 1
    assert bar.value() < bar.maximum() and overlay.follow_live
    QTest.qWait(450)
    assert bar.value() == bar.maximum()
    overlay.close()


def test_ready_requires_final_translation_and_cannot_regress(app):
    overlay = ui.Overlay()
    overlay.update_caption((1, 1, 1), 'Hello', {}, False)
    overlay.render()
    assert 'Listening' in overlay.transcript.toPlainText()
    overlay.update_caption((1, 1, 2), 'Hello there', {}, True)
    overlay.render()
    assert 'Translating' in overlay.transcript.toPlainText()
    assert not overlay.history[(1, 1)]['ready']
    overlay.update_caption((1, 1, 2), 'Hello there', {'en': 'Hello there', 'ar': 'مرحباً'}, True)
    overlay.render()
    assert overlay.history[(1, 1)]['ready']
    assert '✓ Ready' in overlay.transcript.toPlainText()
    overlay.update_caption((1, 1, 1), 'Hello', {'en': 'Hello'}, False)
    assert overlay.history[(1, 1)]['ready']
    overlay.close()


def test_multiple_listening_choices_are_separate_and_saved(app, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, 'ROOT', tmp_path)
    monkeypatch.setattr(ui, 'devices', lambda: [(1, 'Test output', True)])
    monkeypatch.setattr(ui, 'microphones', lambda: [])
    w = ui.Window(load_models=False)
    w.auto_listening.setChecked(False)
    for i in range(w.listening.count()):
        item = w.listening.item(i)
        item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in ['en', 'ar', 'vi'] else Qt.Unchecked)
    assert w.listening_choices() == ['en', 'ar', 'vi']
    assert w.targets() == ['en', 'ar']
    w.close()
    restored = ui.Window(load_models=False)
    assert restored.listening_choices() == ['en', 'ar', 'vi']
    restored.auto_listening.setChecked(True)
    assert restored.listening_choices() is None
    assert not restored.listening.isEnabled()
    restored.close()


def test_saved_microphone_wins_over_windows_default(app, monkeypatch, tmp_path):
    import json
    monkeypatch.setattr(ui, 'ROOT', tmp_path)
    monkeypatch.setattr(ui, 'devices', lambda: [(1, 'Output', True)])
    monkeypatch.setattr(ui, 'microphones', lambda: [(14, 'My headset', False), (15, 'Laptop mic', True)])
    (tmp_path / 'settings.json').write_text(json.dumps({'microphone': 'My headset', 'include_mic': True}))
    w = ui.Window(load_models=False)
    assert w.include_mic.isChecked()
    assert w.microphone.currentData() == 14
    w.refresh()
    assert w.microphone.currentData() == 14
    w.close()


def test_transcript_can_be_moved_and_minimized_without_losing_history(app):
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    overlay = ui.Overlay()
    overlay.display('A retained line', {'en': 'A retained line'})
    app.processEvents()
    original = overlay.pos()
    QTest.mousePress(overlay, Qt.LeftButton, pos=QPoint(100, 20))
    QTest.mouseMove(overlay, QPoint(150, -20))
    QTest.mouseRelease(overlay, Qt.LeftButton, pos=QPoint(150, -20))
    assert overlay.pos() != original
    moved = overlay.pos()
    overlay.toggle_minimized()
    assert overlay.height() == 46 and not overlay.transcript.isVisible()
    overlay.update_caption((2, 1, 1), 'New line while minimized', {'en': 'New line while minimized'}, True)
    overlay.render()
    assert overlay.collapsed and overlay.height() == 46
    overlay.toggle_minimized()
    app.processEvents()
    assert overlay.height() > 46
    assert overlay.pos() == moved
    assert 'A retained line' in overlay.transcript.toPlainText()
    assert 'New line while minimized' in overlay.transcript.toPlainText()
    overlay.close()
