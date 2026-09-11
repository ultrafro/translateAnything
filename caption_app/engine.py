import queue
import re
import threading
import time
from functools import lru_cache
import numpy as np
from .config import ASR_PATH, TRANSLATION_PATH, ASR_LOCALES


def load_pretrained(cls, name, **kwargs):
    try:
        return cls.from_pretrained(name, local_files_only=True, **kwargs)
    except (OSError, TypeError):
        # M2M100Tokenizer passes a missing cached vocab as None to open(), which
        # raises TypeError instead of the usual missing-cache OSError.
        return cls.from_pretrained(name, **kwargs)


def parse_transcript(raw):
    tags = re.findall(r'<([a-z]{2,3})(?:-[A-Za-z]{2,3})?>', raw)
    text = re.sub(r'<[^>]*>', '', raw).strip()
    language = tags[-1] if tags else ('ar' if re.search(r'[\u0600-\u06ff]', text) else None)
    return text, language


@lru_cache(maxsize=32)
def language_identifier(languages):
    from langid.langid import LanguageIdentifier, model
    identifier = LanguageIdentifier.from_modelstring(model, norm_probs=True)
    if languages:
        identifier.set_languages(languages)
    return identifier


def detect_language(text, languages=None):
    # Some short streaming utterances finish without a model-emitted language tag.
    # Script detection is reliable for the English/Arabic conversation use case.
    languages = tuple(sorted(set(languages or ())))
    if len(languages) == 1:
        return languages[0]
    if re.search(r'[\u0600-\u06ff]', text) and (not languages or 'ar' in languages):
        return 'ar'
    return language_identifier(languages).classify(text)[0]


def select_source_language(text, tag=None, languages=None):
    if tag and (not languages or tag in languages):
        return tag
    return detect_language(text, languages)


class ASR:
    def __init__(self, status=lambda _: None):
        import torch
        from transformers import AutoModelForRNNT, AutoProcessor
        torch.set_num_threads(4)
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.dtype = torch.float16 if self.device == 'cuda' else torch.float32
        status(f'Loading Nemotron 3.5 on {self.device.upper()}…')
        self.processor = load_pretrained(AutoProcessor, ASR_PATH)
        self.processor.set_num_lookahead_tokens(13)
        self.model = load_pretrained(AutoModelForRNNT, ASR_PATH, dtype=self.dtype).to(self.device).eval()

    def transcribe(self, blocks, partial=lambda _: None, language='auto', listening_languages=None):
        """Feed real incremental features to the model's cache-aware generator."""
        import torch
        from transformers.generation.streamers import BaseStreamer
        p = self.processor
        if listening_languages and len(listening_languages) == 1:
            language = listening_languages[0]
        language = ASR_LOCALES.get(language, language)
        iterator = iter(blocks)
        recorded = []
        buffer = np.empty(0, np.float32)
        exhausted = False

        def read(size):
            nonlocal buffer, exhausted
            while len(buffer) < size and not exhausted:
                try:
                    block = next(iterator)
                    recorded.append(block)
                    buffer = np.concatenate((buffer, block))
                except StopIteration:
                    exhausted = True
            return buffer[:size]

        audio = read(p.num_samples_first_audio_chunk)
        if not len(audio):
            return '', None
        first = p(np.pad(audio, (0, max(0, p.num_samples_first_audio_chunk - len(audio)))),
                  sampling_rate=16000, is_streaming=True, is_first_audio_chunk=True,
                  language=language, return_tensors='pt').to(self.device, dtype=self.dtype)

        def features():
            nonlocal buffer
            yield first.input_features[:, :p.num_mel_frames_first_audio_chunk, :]
            advance = p.num_mel_frames_first_audio_chunk * p.feature_extractor.hop_length - p.feature_extractor.n_fft // 2
            buffer = buffer[advance:]
            step = p.num_mel_frames_per_audio_chunk * p.feature_extractor.hop_length
            while True:
                audio = read(p.num_samples_per_audio_chunk)
                if not len(audio):
                    break
                # A last zero-padded chunk flushes tokens at an utterance boundary.
                last = exhausted and len(audio) < p.num_samples_per_audio_chunk
                audio = np.pad(audio, (0, max(0, p.num_samples_per_audio_chunk - len(audio))))
                inputs = p(audio, sampling_rate=16000, is_streaming=True,
                           is_first_audio_chunk=False, language=language,
                           return_tensors='pt').to(self.device, dtype=self.dtype)
                yield inputs.input_features
                buffer = buffer[step:]
                if last:
                    break

        class CaptionStreamer(BaseStreamer):
            def __init__(self):
                self.ids = []
                self.last = ''

            def put(self, value):
                self.ids.extend(value.detach().cpu().reshape(-1).tolist())
                text, _ = parse_transcript(p.decode(self.ids, skip_special_tokens=False))
                if text and text != self.last:
                    self.last = text
                    partial(text)

            def end(self):
                pass

        with torch.inference_mode():
            result = self.model.generate(**{**first, 'input_features': features()},
                                         streamer=CaptionStreamer(), return_dict_in_generate=True)
        raw = p.decode(result.sequences, skip_special_tokens=False)
        if isinstance(raw, list):
            raw = raw[0]
        # Auto-language streaming can misread the opening phonemes before enough
        # context arrives. Reconcile the completed bounded utterance using the
        # same Nemotron model with full acoustic context, preserving live updates.
        if recorded:
            full_audio = np.concatenate(recorded)
            interim, tag = parse_transcript(raw)
            refine_language = language
            if language == 'auto' and interim:
                detected_language = select_source_language(interim, tag, listening_languages)
                candidate = ASR_LOCALES.get(detected_language, detected_language)
                if candidate in p.prompt_dictionary:
                    refine_language = candidate
            inputs = p(full_audio, sampling_rate=16000, language=refine_language,
                       return_tensors='pt').to(self.device, dtype=self.dtype)
            with torch.inference_mode():
                final = self.model.generate(**inputs, return_dict_in_generate=True)
            raw = p.decode(final.sequences, skip_special_tokens=False)
            if isinstance(raw, list):
                raw = raw[0]
        text, detected = parse_transcript(raw)
        if not text:
            return '', None
        source = refine_language.split('-')[0] if recorded and refine_language != 'auto' else (
            language.split('-')[0] if language != 'auto' else select_source_language(text, detected, listening_languages))
        return text, source


class Translator:
    def __init__(self, status=lambda _: None):
        import torch
        from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
        status('Loading local translation model…')
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.tokenizer = load_pretrained(M2M100Tokenizer, TRANSLATION_PATH)
        self.model = load_pretrained(M2M100ForConditionalGeneration,
            TRANSLATION_PATH, dtype=torch.float16 if self.device == 'cuda' else torch.float32
        ).to(self.device).eval()

    def translate(self, text, source, targets):
        import torch
        if source not in self.tokenizer.lang_code_to_id:
            raise ValueError('Spoken language was not detected. Select a source language and restart.')
        self.tokenizer.src_lang = source
        inputs = self.tokenizer(text, return_tensors='pt', truncation=True, max_length=384).to(self.device)
        result = {}
        with torch.inference_mode():
            for target in targets:
                if target == source:
                    result[target] = text
                else:
                    tokens = self.model.generate(**inputs, forced_bos_token_id=self.tokenizer.get_lang_id(target),
                                                 max_new_tokens=192, num_beams=2)
                    result[target] = self.tokenizer.batch_decode(tokens, skip_special_tokens=True)[0]
        return result


class Engine:
    def __init__(self, status, caption, ready):
        self.status, self.caption, self.ready = status, caption, ready
        self.stop = threading.Event()
        self.utterances = queue.Queue(maxsize=2)
        self.translations = queue.Queue(maxsize=1)
        self.final_translations = queue.Queue(maxsize=8)
        self.targets = ['en', 'ar']
        self.language = 'auto'
        self.listening_languages = None
        self.session = 0
        self.counter = 0
        self.asr = self.translator = None
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.translation_thread = threading.Thread(target=self.translate_loop, daemon=True)

    def submit(self, utterance):
        try:
            self.utterances.put_nowait((self.session, utterance))
        except queue.Full:
            self.status('Recognition is falling behind. Skipping older audio to stay live.')
            try:
                self.utterances.get_nowait()
            except queue.Empty:
                pass
            self.utterances.put_nowait((self.session, utterance))

    def run(self):
        try:
            self.asr = ASR(self.status)
            self.translator = Translator(self.status)
            self.translation_thread.start()
            self.ready()
            while not self.stop.is_set():
                try:
                    session, utterance = self.utterances.get(timeout=.1)
                except queue.Empty:
                    continue
                if session != self.session:
                    continue
                self.counter += 1
                sequence = self.counter
                revision = 0
                last_translation = 0
                language = self.language
                listening_languages = tuple(self.listening_languages) if self.listening_languages else None

                def update(text):
                    nonlocal revision, last_translation
                    revision += 1
                    identity = (session, sequence, revision)
                    self.caption(identity, text, {}, False)
                    if len(text) >= 12 and time.monotonic() - last_translation >= 1.5:
                        last_translation = time.monotonic()
                        source = language.split('-')[0] if language != 'auto' else detect_language(text, listening_languages)
                        self.queue_translation(identity, text, source)

                try:
                    self.status('Recognizing captured speech…')
                    text, source = self.asr.transcribe(utterance.samples(self.stop), update, language, listening_languages)
                    if text and session == self.session:
                        identity = (session, sequence, revision + 1)
                        self.caption(identity, text, {}, True)
                        self.queue_translation(identity, text, source, final=True)
                    elif session == self.session and not self.stop.is_set():
                        self.status('Audio received, but no words recognized • check the microphone and listening languages')
                except Exception as exc:
                    self.status(f'Recognition error: {exc}')
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.status(f'Model loading failed: {exc}. See README for repair instructions.')

    def queue_translation(self, identity, text, source, final=False):
        if identity[0] != self.session or self.stop.is_set():
            return
        destination = self.final_translations if final else self.translations
        if destination.full():
            try:
                destination.get_nowait()
            except queue.Empty:
                pass
            if final:
                self.status('Translation is falling behind; an older segment was skipped.')
        destination.put_nowait((identity, text, source, tuple(self.targets), final))

    def translate_loop(self):
        completed = {}
        while not self.stop.is_set():
            try:
                try:
                    item = self.final_translations.get_nowait()
                except queue.Empty:
                    item = self.translations.get(timeout=.1)
                identity, text, source, targets, final = item
            except queue.Empty:
                continue
            if identity[0] != self.session:
                continue
            key = identity[:2]
            if identity <= completed.get(key, (-1, -1, -1)):
                continue
            try:
                translated = self.translator.translate(text, source, targets)
                self.caption(identity, text, translated, final)
                if final and identity[0] == self.session and not self.stop.is_set():
                    self.status('Caption ready • listening for more speech')
                completed[key] = identity
                if len(completed) > 50:
                    del completed[next(iter(completed))]
            except Exception as exc:
                self.status(f'Translation error: {exc}')
