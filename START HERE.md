# Put Translate Anything on another computer

## Windows

1. Open https://github.com/ultrafro/translateAnything/releases/latest on the other computer.
2. Download **Translate-Anything-Windows.zip**. Right-click it → **Extract All**.
3. Open the extracted folder and double-click **Start Captions.bat**.
4. Leave setup open. The first start downloads dependencies and models; keep the internet connected.
5. Click **⚙** to choose your audio output and caption languages. When the app says **Ready**, click **Start live captions**.

The transcript is the main window. Click **⚙** to open or close settings inside it. To include your voice, open settings, check **Include my microphone** and choose your mic. Start/Stop stays at the bottom in either view. **—** collapses the window; **×** closes the app.
Next time, just open **Start Captions.bat** again. No Python installation or API key needed.

Keep the whole folder together. Allow roughly 12 GB of free disk space. Windows 10/11 x64 is required; a recent NVIDIA GPU is recommended. CPU recognition can lag behind speech.

**Already have the complete working Windows folder?** Copy the entire `Translate Anything` folder to the other computer, including `runtime` and `models`. Open **Start Captions.bat** there. Choose the new computer's audio devices. No need to download models again.

## Mac (M1 or newer, macOS 14 or later)

1. Open https://github.com/ultrafro/translateAnything/releases/latest.
2. Download **Translate-Anything-Mac-Apple-Silicon.tar.gz** and double-click it to extract.
3. Open the folder and double-click **Start Captions.command**. If macOS blocks it, use **System Settings → Privacy & Security → Open Anyway** after checking you downloaded this release.
4. Leave setup open while it downloads. Allow microphone access when macOS asks.
5. Click **⚙**. To caption your voice, select **Microphone only**, check **Include my microphone**, choose your mic, and click **Start live captions** after **Ready** appears.

For sound from other Mac apps, do this once:

1. Install **BlackHole 2ch** from https://existential.audio/blackhole/ and restart if asked.
2. Open **Audio MIDI Setup** (Applications → Utilities). Click **+ → Create Multi-Output Device**.
3. Check your speakers/headphones and **BlackHole 2ch**. Use your speakers/headphones as the primary device and enable drift correction for BlackHole.
4. In **System Settings → Sound → Output**, select that **Multi-Output Device**.
5. In Translate Anything, click **Refresh**, select **BlackHole 2ch**, and start captions. You can also include your microphone.

Keep the folder somewhere writable, such as your home folder. Keep Terminal open while captions run. This Mac build uses CPU inference, so captions may arrive more slowly than on an NVIDIA Windows PC. Intel Macs are not supported by this build.

## Updates

The transcript says **Following live** while it scrolls gently with new captions. Scroll up to pause it; click **Resume live** to catch up. Your reading position stays on the same entry when earlier translations change or old entries are removed.

The app checks GitHub whenever it opens. Compatible app updates download automatically and install the next time you open it. Your models and settings stay in place. The settings window shows update status. Offline captions still work with models already downloaded.

A release needing new Python dependencies will say a fresh download is required. Download the new package using the same steps above. Always extract the archive before opening the app.
