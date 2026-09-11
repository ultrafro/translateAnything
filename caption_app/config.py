import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ['HF_HOME'] = str(ROOT / 'models')
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
ASR_MODEL = 'nvidia/nemotron-3.5-asr-streaming-0.6b'
TRANSLATION_MODEL = 'facebook/m2m100_418M'
ASR_PATH = str(ROOT / 'models/asr') if (ROOT / 'models/asr/config.json').exists() else ASR_MODEL
TRANSLATION_PATH = str(ROOT / 'models/translation') if (ROOT / 'models/translation/config.json').exists() else TRANSLATION_MODEL
LANGUAGES = {'en': 'English', 'ar': 'Arabic', 'es': 'Spanish', 'fr': 'French',
             'de': 'German', 'it': 'Italian', 'pt': 'Portuguese', 'ru': 'Russian',
             'tr': 'Turkish', 'hi': 'Hindi', 'ja': 'Japanese', 'ko': 'Korean',
             'zh': 'Chinese', 'uk': 'Ukrainian', 'nl': 'Dutch', 'vi': 'Vietnamese',
             'pl': 'Polish', 'sv': 'Swedish', 'cs': 'Czech', 'ro': 'Romanian'}
ASR_LOCALES = dict(zip(LANGUAGES, [
    'en-US', 'ar-AR', 'es-ES', 'fr-FR', 'de-DE', 'it-IT', 'pt-PT', 'ru-RU',
    'tr-TR', 'hi-IN', 'ja-JP', 'ko-KR', 'zh-CN', 'uk-UA', 'nl-NL', 'vi-VN',
    'pl-PL', 'sv-SE', 'cs-CZ', 'ro-RO']))
