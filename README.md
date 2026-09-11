# Translate Anything

A local Windows and Apple Silicon Mac app that keeps a live, translated conversation transcript at the bottom left of your screen. English and Arabic are selected by default; check additional languages to display them together.

## Start

**[Simple instructions for another computer](START%20HERE.md)** · **[Download Windows or Mac](https://github.com/ultrafro/translateAnything/releases/latest)**

The public downloads include portable Python. Dependencies and models download on first start. Windows: open `Start Captions.bat`. Mac: open `Start Captions.command`; macOS 14+ on Apple Silicon is required. See the short guide for Mac system-audio setup. Mac inference uses CPU and can fall behind live speech.

Double-click **Start Captions.bat**. Wait for **Ready**, select the audio output your apps are using, choose caption languages, and click **Start live captions**. To caption your own voice too, check **Include my microphone** and select your microphone before starting. **Preview** shows the overlay without capturing audio.

Under **Listening languages**, uncheck **Detect all languages automatically** and check the languages people will speak: for example English + Arabic, English + Vietnamese, or all three. These choices are independent of **Caption languages**, which control the translated text you read. A single listening language forces that language. With multiple choices, Nemotron initially streams in automatic mode, then the selected choices guide local language detection and the final language-conditioned recognition pass. The model accepts one language prompt at a time, so this is not a strict audio-language filter; very short speech and rapid mid-sentence switches can still be ambiguous. Enable **Detect all languages automatically** to remove the restriction.

If your voice does not appear, stop captions, refresh the device list, select the actual microphone, enable **Include my microphone**, and restart. Watch the separate **Mic signal** meter while speaking. If it stays empty, check that the selected microphone is unmuted and receiving input in Windows. If it moves only slightly, increase **Mic boost** before restarting. Connecting a microphone alone does not enable capture. Use only one app instance to avoid confusion between settings windows.

The developer's **dist/Translate Anything** folder is a fully provisioned Windows build. Copy that entire folder to another Windows x64 computer to reuse its Python, dependencies, and model weights. The smaller public release downloads dependencies and weights on first start. Neither needs an existing Python installation, API key, Docker, or cloud speech service. NVIDIA acceleration needs a compatible driver for CUDA 13; CPU fallback may not keep up with live speech.

The transcript stays above normal windows and retains the latest 50 speech segments. It does not disappear during silence or when you stop capture. New updates follow the bottom, with a small gap below the text. Scrolling up pauses auto-scroll so you can read older lines; scrolling back to the bottom resumes it. Drag the title bar to move the panel. Its **—** button collapses it to a small bar; **▢** expands it again, with history preserved. **Clear** removes the retained transcript. History stays in memory until cleared or the app closes. Text defaults to a smaller 18-point size and can be adjusted in settings. Stop captions before changing languages or audio devices. Refresh devices after connecting headphones. Minimize the settings window to keep only the transcript visible; closing it quits.

Unfinished text is muted and labeled **Listening…** or **Translating…**. Once both recognition and the final translation finish, text becomes white with a green **✓ Ready** label. Ready indicates that processing is complete, not that the translation is guaranteed correct.

## Behavior

- Captures the mix of applications playing through the selected Windows output, including browsers, media players, and calls. **Include my microphone** optionally mixes in the selected microphone, so your voice is captured even while system audio is silent. Other output devices are not captured simultaneously. Headphones help prevent your microphone from picking up the same playback twice; there is no acoustic echo cancellation.
- Nemotron streams provisional original-language text. Translation refreshes during speech, approximately every 1.5 seconds plus inference time, and again when the segment ends. A full-context pass over each completed segment corrects provisional recognition before final translation. Partial translations can change as more words arrive.
- Each speech segment gets a timestamp and a row for each selected target language. Provisional updates revise the same entry; new speech segments append to the conversation. The panel accepts mouse input so you can scroll its history.
- Automatic language tags are used when emitted by Nemotron; a local text-language detector handles short utterances without tags. Very short or ambiguous speech may need a manually selected source language. Overlapping speakers and rapid mid-sentence language changes can reduce accuracy. There is no speaker diarization.
- The model uses 1.12-second streaming chunks to improve automatic language detection at the beginning of speech. Actual caption delay includes audio buffering and inference. Initial translated captions typically take a few seconds; recognition updates arrive sooner. More target languages increase latency. Exact results for this computer are recorded in the test logs.
- Silence gating prevents idle transcription; speech in music or very quiet audio can still be missed or misrecognized. Exclusive fullscreen apps may cover overlays; use borderless/windowed mode if needed. Protected audio may not be capturable.

## Models and implementation

ASR: [NVIDIA Nemotron 3.5 ASR Streaming 0.6B](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b), the latest multilingual Nemotron ASR release found in NVIDIA's official sources on September 11, 2026. NVIDIA lists English and Arabic as transcription-ready languages. The app uses the native cache-aware Transformers streaming API with automatic source-language prompting.

Translation: [Meta M2M100 418M](https://huggingface.co/facebook/m2m100_418M), run locally and independently of ASR. Nemotron performs speech recognition; it does not itself translate speech into each target language.

Application logic is Python. PySide6, PyTorch, PortAudio, and other Python dependencies include their normal native binary libraries; there is no custom compiled application, browser frontend, or external inference server. The bundled interpreter is official CPython 3.12.10 for Windows x64. Dependencies are pinned in `requirements.lock.txt`.

The fully provisioned development release includes FP16 model snapshots in `models/asr` and `models/translation`. Public first-install packages download models into their Hugging Face cache under `models/`; after setup they work offline. Audio and transcripts are not sent anywhere. Settings stay in `settings.json`. Ordinary use does not save captured audio or transcripts. Test tools save synthetic/public-fixture transcripts to `logs/`.

## Verification

Run these from this folder in PowerShell:

```powershell
.\runtime\python.exe -s -X utf8 -m pytest tests -q
.\runtime\python.exe -s -X utf8 tools/check_end_to_end.py
.\runtime\python.exe -s -X utf8 tools/check_live_app.py
```

The integration tests play speech audibly through your default Windows output. The first tests English and Arabic recognition, bidirectional translation, live loopback capture, partial updates, and overlay placement. The GUI test uses the actual Start/Stop buttons and workers, plays English followed by Arabic, checks translated captions and restart behavior, and forces Hugging Face offline mode. Results and screenshots are in `logs/end_to_end.json` and `logs/live-app-test.json`.

English fixture: generated with Windows System.Speech. Arabic fixture: [Google FLEURS, ar_eg test row 0](https://huggingface.co/datasets/google/fleurs). Fixtures and local test reports are not published in this repository; model integration tools need those local fixtures. These checks are not a comprehensive accuracy benchmark across all languages or apps.

## Troubleshooting and rebuilding

If audio is not detected, select the output on which it is actually playing and watch the audio meter. Stop, refresh, and restart after changing headphones. If another app occupies the GPU, close that workload and restart captions. Use **Start with console.cmd** to see diagnostics; GUI-launch errors are written to `logs/app.log`.

To rebuild dependencies from source, use an existing Python 3.12 installation to run `python setup_portable.py`. This downloads the official embeddable runtime if missing and installs the pinned dependencies into `runtime/`. Launchers always use `-s` to exclude packages from your user Python installation. To build the release from the development folder, run `runtime\python.exe -s -X utf8 tools/build_portable.py`.

## Automatic updates

On startup, a background worker checks stable releases in `ultrafro/translateAnything`. Compatible updates download automatically and install on the next launch, before models load. GitHub SHA-256 asset digests, per-file hashes, archive paths, sizes, and versions are checked. A recovery journal restores the previous files after an interrupted installation. Application Python files and documentation update; models, settings, logs, launchers, and the runtime are preserved. Offline checks do not block captions.

Releases within `UPDATE_API = 1` must use the existing dependencies and launchers. Maintainers must bump that contract when new dependencies or launchers become necessary, and publish fresh installation packages. Such releases report that a new portable download is needed. The update channel trusts this GitHub repository; it is not independently code-signed.

## macOS

CoreAudio capture uses [python-sounddevice](https://python-sounddevice.readthedocs.io/) and [BlackHole's Multi-Output setup](https://github.com/ExistentialAudio/BlackHole/wiki/Multi-Output-Device). Microphone-only mode needs no BlackHole. Portable Python comes from [Astral python-build-standalone](https://github.com/astral-sh/python-build-standalone), pinned by SHA-256. The Mac lock uses official Apple Silicon PyTorch wheels.

GitHub Actions runs regression tests and native import checks on Windows and Mac. Automated device callbacks exercise real resampling, mixing and segmentation, but cannot verify Mac microphone permissions, physical routing or recognition speed. The Windows development machine was also tested through the real Nemotron and translation models with quiet simulated microphone speech.

## Publishing

Update `caption_app/version.py`, run the tests, then run `python tools/package_release.py` using Python 3.12. Publish a stable `vX.Y.Z` release with both installation archives, `app-update.zip` and `SHA256SUMS.txt` from `dist/releases`. Never publish settings, logs, recordings or private test metadata. Model weights are downloaded from their original publishers.
