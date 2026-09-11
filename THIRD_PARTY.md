# Third-party components

This app bundles independently licensed components. Their license and metadata files remain in `runtime/Lib/site-packages` and `runtime/LICENSE.txt`.

- CPython 3.12.10: Python Software Foundation license; https://www.python.org/downloads/release/python-31210/
- PySide6 / Qt: LGPLv3/GPLv3/commercial licensing; https://doc.qt.io/qtforpython-6/licenses.html . The Python source and dynamically loaded Qt libraries are provided separately and can be replaced by compatible versions.
- PyTorch: BSD-style license; https://github.com/pytorch/pytorch/blob/main/LICENSE
- Transformers: Apache 2.0; https://github.com/huggingface/transformers/blob/main/LICENSE
- NVIDIA Nemotron 3.5 ASR weights: Open Model License (OpenMDW 1.1), as identified by NVIDIA's model card; https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b
- Meta M2M100: MIT, as identified by its model card; https://huggingface.co/facebook/m2m100_418M
- Google FLEURS Arabic test fixture: CC BY 4.0; https://huggingface.co/datasets/google/fleurs . Test row 0, ar_eg, ID 1993. Text and provenance are retained in `tests/fixtures/arabic_metadata.json`.

See `requirements.lock.txt` for the complete dependency inventory. NVIDIA driver software is supplied by the computer, not this folder.

- Mac portable Python: Astral python-build-standalone; CPython and included components retain their licenses in the runtime archive. https://github.com/astral-sh/python-build-standalone
- python-sounddevice: MIT; https://github.com/spatialaudio/python-sounddevice
- BlackHole: GPL-3.0, installed separately by the user; https://github.com/ExistentialAudio/BlackHole

Public source and first-install packages do not include model weights or test audio. Local fixture metadata referenced above is not published.
