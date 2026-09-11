import threading
import numpy as np
from caption_app.audio import Segmenter, BLOCK
from caption_app.engine import parse_transcript


def test_silence_does_not_create_captions():
    found = []
    s = Segmenter(found.append)
    for _ in range(100): s.feed(np.zeros(BLOCK, np.float32))
    assert not found


def test_segment_preserves_preroll_and_finishes():
    found = []
    s = Segmenter(found.append)
    for _ in range(20): s.feed(np.zeros(BLOCK, np.float32))
    for _ in range(20): s.feed(np.ones(BLOCK, np.float32) * .1)
    for _ in range(35): s.feed(np.zeros(BLOCK, np.float32))
    assert len(found) == 1 and found[0].ended.is_set()
    blocks = list(found[0].samples(threading.Event()))
    assert len(blocks) == 64
    assert np.max(blocks[0]) == 0
    assert np.max(blocks[10]) > .09


def test_continuous_audio_is_bounded():
    found = []
    s = Segmenter(found.append)
    for _ in range(1300): s.feed(np.ones(BLOCK, np.float32) * .1)
    s.finish()
    assert len(found) == 3
    assert all(u.ended.is_set() for u in found)


def test_language_tags():
    assert parse_transcript('<blank>Hello world.<en-US>') == ('Hello world.', 'en')
    assert parse_transcript('مرحباً بالعالم.<ar-AR>') == ('مرحباً بالعالم.', 'ar')
    assert parse_transcript('Hello') == ('Hello', None)


def test_stop_unblocks_waiting_audio():
    from caption_app.audio import Utterance
    stop = threading.Event(); stop.set()
    assert list(Utterance().samples(stop)) == []


def test_all_source_languages_use_supported_nemotron_prompts():
    from caption_app.config import ASR_LOCALES, LANGUAGES
    from transformers.models.nemotron3_5_asr.processing_nemotron3_5_asr import DEFAULT_PROMPT_DICTIONARY
    assert set(ASR_LOCALES) == set(LANGUAGES)
    assert all(locale in DEFAULT_PROMPT_DICTIONARY for locale in ASR_LOCALES.values())


def test_microphone_keeps_working_when_system_output_is_silent():
    from caption_app.audio import FrameMixer
    mixer = FrameMixer(2)
    mic = np.ones(BLOCK, np.float32) * .2
    mixer.put(1, mic)
    np.testing.assert_allclose(mixer.read(), mic)
    mixer.put(0, mic)
    mixer.put(1, mic)
    np.testing.assert_allclose(mixer.read(), mic * 2)
    np.testing.assert_allclose(mixer.read(), 0)


def test_final_translation_is_not_replaced_by_new_partial():
    from caption_app.engine import Engine
    engine = Engine(lambda _: None, lambda *args: None, lambda: None)
    engine.queue_translation((0, 1, 2), 'Finished', 'en', final=True)
    for i in range(5): engine.queue_translation((0, 2, i), 'New words', 'en')
    assert engine.final_translations.get_nowait()[1] == 'Finished'
    assert engine.translations.qsize() == 1


def test_selected_listening_languages_guide_source_detection():
    from caption_app.engine import select_source_language
    assert select_source_language('Hello, how are you today?', None, ['en', 'ar']) == 'en'
    assert select_source_language('مرحباً كيف حالك اليوم؟', None, ['en', 'ar']) == 'ar'
    assert select_source_language('Xin chào, hôm nay bạn có khỏe không?', None, ['en', 'vi']) == 'vi'
    assert select_source_language('Xin chào, hôm nay bạn có khỏe không?', 'de', ['en', 'ar', 'vi']) == 'vi'
    assert select_source_language('Hello', 'en', ['en', 'ar', 'vi']) == 'en'
    assert select_source_language('Hello', None, ['vi']) == 'vi'
