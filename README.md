<div align="center">
  <img src="desktop/icon.png" width="112" height="112" alt="Poros">
  <h1>Poros</h1>
  <p><strong>Use your phone as your PC's microphone and camera.</strong></p>
  <p>No account. Nothing leaves your Wi‑Fi.</p>

  <p>
    <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-blue?style=flat-square" alt="Platform">
    <img src="https://img.shields.io/badge/License-GPLv3-green?style=flat-square" alt="License">
  </p>
</div>

---

## What is this?

Your desktop either has no microphone, or a poor one, or no camera worth using. Poros turns the
phone you already own into both:

- **A microphone** — your voice goes from the phone into Discord, Zoom, OBS, in‑game chat, anything
  that lets you pick a microphone.
- **A camera** — the phone camera streams to the PC and appears as a normal webcam, so meetings,
  OBS and browsers can use it directly.

Everything travels phone → PC over your own Wi‑Fi, peer‑to‑peer. There is no account and no cloud.

- **Nothing to install on the phone for the microphone** — the phone can just open a web page.
- **Nothing goes over the internet.** Audio and video stay on the local network.
- **Works with any app** that lets you choose a microphone or a camera.

## Getting started

**You need:** a Windows, Linux or macOS PC, a phone, and both on the same Wi‑Fi.

**1. Download Poros for your PC** from the [Releases page](https://github.com/timuela/Poros/releases):

| Your PC | File | What to do |
| --- | --- | --- |
| Windows (64-bit) | `Poros-Host-Setup-<version>-windows-x64.exe` | Run it — installs with a Start Menu shortcut |
| Windows (64-bit) | `Poros-Host-Portable-<version>-windows-x64.exe` | One single file — just run it, nothing to unpack |
| Linux | `Poros-Host-<version>-linux-x64.tar.gz` | Extract, then run `Poros` |
| macOS (Apple silicon) | `Poros-Host-<version>-macos-arm64.tar.gz` | Extract, then run `Poros` |
| macOS (Intel) | `Poros-Host-<version>-macos-x64.tar.gz` | Extract, then run `Poros` |

**2. Run it.** Poros needs a virtual audio device to play into, and sets one up like this:

- **Windows** — installs it for you on first launch (10–20 seconds), and Windows asks for
  permission. Say yes.
- **Linux** — creates one instantly.
- **macOS** — install [BlackHole](https://github.com/ExistentialAudio/BlackHole) first:
  `brew install blackhole-2ch`. The app tells you if it's missing.

**3. Open the address on your phone.** The PC window shows something like `https://192.168.1.42:5000`,
and a QR code you can scan instead of typing. Your phone and PC must be on the same Wi‑Fi.

**4. Accept the security warning.** Your phone will say the connection isn't private. That's
expected — browsers only allow microphone access over HTTPS, so Poros makes its own certificate.
Tap **Advanced → Proceed**.

**5. Type the PIN** shown on the PC window. (You can change it, or turn the PIN off entirely, in
Settings.)

**6. Point your app at Poros's microphone.** In the game, Discord, Zoom, OBS — wherever — pick
the virtual device as the microphone input:

| Your PC | Choose this microphone |
| --- | --- |
| Windows | `CABLE Output (VB-Audio Virtual Cable)` |
| Linux | `Poros Virtual Output Monitor` |
| macOS | `BlackHole 2ch` |

*(On Windows you'll also see a `CABLE Input` device — that's the other end of the same cable.
The app plays into it, so you record from `CABLE Output`.)*

**7. Talk.**

## Camera

The phone camera becomes a normal Windows webcam named **Poros Virtual Camera**.

1. Open the **Camera** screen on the phone app so it can announce itself to the PC.
2. On the PC, press **Camera** to open the camera window. The virtual camera is installed the
   first time you start streaming (Windows asks for permission — say yes).
3. Pick a resolution and frame rate, then press **Start camera**. The preview appears on the PC
   and *Poros Virtual Camera* becomes selectable in Zoom, OBS, the browser — anywhere.

From the camera window you can switch between the front and back camera, turn the torch on,
mirror or rotate the image, zoom, and take a snapshot (saved under `Pictures\Poros`).

The phone encodes with its hardware encoder, so it can stream up to **4K at 60 fps** where the
phone supports it. Wired/close Wi‑Fi gives the smoothest result.

To remove the virtual camera later, use the **Uninstall** button next to the virtual camera
status in the camera window.

## On the PC

The window is small on purpose. From it you can:

- See whether your phone is connected.
- Pick the audio output device Poros plays into (it finds the virtual one automatically).
- Set the volume, and mute — the tray icon can mute too.
- Open the **Camera** window for the live preview and virtual‑camera controls.
- Copy any of your PC's addresses (Wi‑Fi, Ethernet, VPN, Tailscale), and show a QR code for
  whichever network your phone is actually on.
- Change the **port**, the **PIN**, the **language** (English / 中文 / Tiếng Việt), whether it
  starts with Windows, and whether closing the window quits or hides to the tray.

## The phone app

**`Poros-Client-<version>.apk`** from the same [Releases page](https://github.com/timuela/Poros/releases).
Needs Android 8.0 or newer.

- Keeps streaming with the screen off (it runs as a proper foreground service).
- The **Camera** screen streams the phone camera to the PC's virtual webcam.
- Save your PCs as **profiles** and switch between them instead of retyping the address.
- Type just the IP — the port defaults to `5000`.

## Troubleshooting

**My phone says the connection isn't private.**
That's normal and safe. It's Poros's own certificate, not a broken site. Tap **Advanced**, then
**Proceed**.

**My PC suddenly has no sound (Windows).**
The driver installer sometimes makes the virtual cable your default speaker. Click the speaker
icon in the taskbar and switch back to your real speakers or headphones. Poros reminds you about
this after installing.

**The virtual camera doesn't appear in Zoom/OBS.**
Install it from the camera window (**Install**), then reopen the app that should see it. Some
apps only list cameras when they start.

**No audio at all on Linux.**
Install PortAudio: `sudo apt install libportaudio2`. It's a system library, so it isn't bundled
inside the app.

**"pactl: command not found" (Linux).**
You need PulseAudio or PipeWire. Most desktops already have one; if not, `sudo apt install
pulseaudio-utils` (Debian/Ubuntu) or `sudo pacman -S pulseaudio` (Arch).

**My phone can't reach the PC.**
Check both are on the same Wi‑Fi, and that you used the address the PC is actually showing —
if you're on a VPN or Tailscale, pick that address. Guest Wi‑Fi and "client isolation" block
phone-to-PC traffic entirely.

**The camera stutters or drops at 4K.**
4K/60 is heavy; lower the resolution or frame rate in the camera window, or move the phone and
PC onto the same access point.

**Uninstalling the driver on Windows fails.**
Run Poros as administrator for that, and restart the PC afterwards to clear the audio routing.

## Building from source

Requires **Python 3.11 or newer** (PySide6 supports 3.14 from 6.10; the CI builds on 3.11).

```bash
git clone https://github.com/timuela/Poros.git
cd Poros

python -m venv .venv

# Windows
.\.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-windows.txt

# Linux / macOS
source .venv/bin/activate
pip install -r requirements.txt

# Build the desktop host — Windows
.\build.bat

# Build the desktop host — Linux / macOS
./build.sh
```

The app lands in `dist/Poros/`. On Windows, `dev\build-host.ps1` also produces the single-file
portable exe, and `dev\build-installer.ps1` builds the installer (needs [Inno Setup 6](https://jrsoftware.org/isdl.php)).

The Windows build bundles `virtualcam/poros-cam.dll`, the DirectShow sender that publishes the
virtual webcam; it is registered per machine the first time you install or start the camera.

For the Android client, open `android/` in Android Studio (JDK 17) or use the CLI:

```bash
cd android
./gradlew assembleRelease        # Windows: gradlew.bat assembleRelease
```

The APK is written to `android/app/build/outputs/apk/release/app-release.apk`.

## License

[GPL-3.0](LICENSE) — free to use, modify and share, as long as derivatives stay open under the
same licence.
