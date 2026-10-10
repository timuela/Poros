import asyncio
import io
import json
import logging
import os
import sys
import threading
import time
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from desktop import camera as video
from desktop import startup
from desktop.camera_ui import AdjustDialog, QualityDialog
from desktop.devices import default_output_index, find_output_index, list_output_devices
from desktop.session import DesktopSession
from desktop.ui import MainWindow

log = logging.getLogger(__name__)


def _load_icon(path):
    """An icon that carries the sizes Windows actually asks for.

    Taskbar and title-bar buttons are 16-32px. Built from a single 256px
    source the QIcon has no small pixmap to offer, which is how the shell
    ends up drawing its generic placeholder, so add explicit sizes.
    """
    source = QPixmap(path)
    if source.isNull():
        return QIcon(path)

    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(
            source.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
    return icon


def _apply_windows_taskbar_identity():
    """Give the process the right taskbar identity, when there is one to use.

    From source the process is python.exe, and Windows draws the taskbar button
    from that host process's identity - Python's own logo - no matter what icon
    the window carries, so an explicit id makes the shell use the window icon.

    An installed build has a Start Menu shortcut registering the same id, so it
    is safe and correct to use it there too: the shell resolves the icon from
    the shortcut. A portable exe has no shortcut, and an unregistered id makes
    the shell draw its generic placeholder - so leave it alone and let Windows
    derive the identity from the exe path, whose embedded icon is correct.

    Must run before the QApplication is created.
    """
    if sys.platform != "win32":
        return
    app_id = startup.installed_app_id()
    if not app_id:
        if getattr(sys, "frozen", False):
            return
        app_id = "Poros.Desktop.Host"
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        log.debug("could not set the AppUserModelID", exc_info=True)


def _detect_language():
    """Default to English; a language chosen in Settings overrides it."""
    return "en_us"


class Translator:
    """Loads the same webui/lang/*.json files the browser UI uses."""

    def __init__(self, webui_dir, language=None):
        self._dir = webui_dir
        self.lang = language or _detect_language()
        self._data = {}
        self.load(self.lang)

    def load(self, language):
        self.lang = language
        self._data = {}
        try:
            path = os.path.join(self._dir, "lang", f"{language}.json")
            with open(path, "r", encoding="utf-8") as handle:
                self._data = json.load(handle)
        except Exception:
            log.debug("could not load language file for %s", language)

    def __call__(self, key, fallback=""):
        return self._data.get(key, fallback)


def _style_path():
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "style.qss"),
        os.path.join(getattr(sys, "_MEIPASS", ""), "desktop", "style.qss"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def _make_qr_png(url):
    try:
        import segno

        buffer = io.BytesIO()
        segno.make(url, error="h").save(buffer, kind="png", scale=4, border=2)
        return buffer.getvalue()
    except Exception as exc:
        log.debug("QR generation failed: %s", exc)
        return None


class Feedback(QObject):
    """Thread-safe bridge: emitted from the asyncio thread, delivered on the UI thread."""

    presenceChanged = Signal(bool)
    linkStateChanged = Signal(str)
    rtcStateChanged = Signal(str)
    mutedChanged = Signal(bool)
    errorRaised = Signal(str)
    driverFinished = Signal(bool, str)
    addressesReady = Signal(int, list)
    devicesReady = Signal(list, object)
    cameraDescriptorChanged = Signal(object)
    cameraStatusChanged = Signal(str, str)
    cameraStatsChanged = Signal(object)
    cameraVirtualInstalled = Signal(bool, str)

    def set_presence(self, connected):
        self.presenceChanged.emit(bool(connected))

    def set_camera_descriptor(self, descriptor):
        self.cameraDescriptorChanged.emit(descriptor)

    def set_camera_status(self, state, detail=""):
        self.cameraStatusChanged.emit(str(state), str(detail))

    def set_camera_stats(self, sample):
        self.cameraStatsChanged.emit(sample)

    def set_link_state(self, state):
        self.linkStateChanged.emit(str(state))

    def set_rtc_state(self, state):
        self.rtcStateChanged.emit(str(state))

    def set_muted(self, muted):
        self.mutedChanged.emit(bool(muted))

    def report_error(self, message):
        self.errorRaised.emit(str(message))


class AsyncRunner:
    """Runs the asyncio event loop (signalling + WebRTC) on a background thread."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="poros-async", daemon=True)
        self._thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def schedule(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def stop(self):
        try:
            self.loop.call_soon_threadsafe(self.loop.stop)
        except Exception:
            pass


def _settings_path():
    """Keep settings next to the executable so the build stays portable."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "poros-host.ini")


class DesktopApp:
    def __init__(self, qapp, platform, version, webui_dir, icon_path, server):
        self._qapp = qapp
        self._platform = platform
        self._version = version
        self._server = server
        self._settings = QSettings(_settings_path(), QSettings.IniFormat)
        saved_language = self._settings.value("language")
        self._translator = Translator(webui_dir, saved_language or None)
        self._t = self._translator
        # Driver install/uninstall results come back from the platform layer, so
        # it needs the same translator to answer in the chosen language.
        set_platform_translator = getattr(platform, "set_translator", None)
        if set_platform_translator is not None:
            set_platform_translator(self._t)

        self._runner = AsyncRunner()
        self._feedback = Feedback()
        self._session = DesktopSession(self._feedback, platform, self._t)
        self._session.set_scheduler(self._runner.schedule)

        self._current_device = None
        self._hint_shown = False
        self._muted = False
        self._active = False
        self._auto_listen_pending = False

        # Video: one DirectShow sender + one RTSP receiver for the whole app.
        self._virtual_cam = video.VirtualCamera()
        self._receiver = video.CameraReceiver(
            on_frame=self._on_video_frame,
            on_state=self._on_video_state,
            on_stats=self._on_video_stats,
        )
        self._frame_lock = threading.Lock()
        self._latest_frame = None
        self._camera_descriptor = None
        self._camera_streaming = False
        self._camera_back = True
        self._camera_size = (1920, 1080)
        self._rotation = 0
        self._pending_camera_start = False
        self._quality_dialog = None
        self._adjust_dialog = None
        self._autofocus = True
        self._focus_distance = 0
        # Stream settings the desktop owns; the phone is told about them.
        self._camera_settings = {
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "codec": "h264",
            "adaptive": False,
            "bitrate": 6000,
            "min_bitrate": 2000,
            "max_bitrate": 12000,
            "transport": "tcp",
        }

        self._window = MainWindow(self._t, version, self._translator.lang)
        self._window.set_level_provider(self._session.level)
        self._window.set_frame_source(self._take_frame)
        self._window.set_gain(1.0)
        self._window.on_hidden = self._on_window_hidden

        self._connect_signals()
        self._tray = self._build_tray(icon_path)

    # ------------------------------------------------------------------
    # wiring
    # ------------------------------------------------------------------
    def _connect_signals(self):
        self._window.connectRequested.connect(self._on_connect)
        self._window.disconnectRequested.connect(self._on_disconnect)
        self._window.muteToggled.connect(lambda: self._session.toggle_mute(broadcast=False))
        self._window.gainChanged.connect(self._session.set_gain)
        self._window.deviceChanged.connect(self._on_device_changed)
        self._window.aboutRequested.connect(self._on_about)
        self._window.languageChanged.connect(self._on_language_changed)
        self._window.requirePinChanged.connect(self._on_require_pin_changed)
        self._window.regeneratePinRequested.connect(self._on_regenerate_pin)
        self._window.pinChanged.connect(self._on_pin_changed)
        self._window.startupChanged.connect(self._on_startup_changed)
        self._window.closeToTrayChanged.connect(self._on_close_to_tray_changed)
        self._window.quitRequested.connect(self._quit)
        self._window.addressSelected.connect(self._on_address_selected)
        self._window.portChangeRequested.connect(self._on_port_requested)
        self._window.cameraToggleRequested.connect(self._on_camera_toggle)
        self._window.rotateRequested.connect(self._on_rotate)
        self._window.flipRequested.connect(self._on_flip)
        self._window.swapRequested.connect(self._on_swap)
        self._window.torchToggled.connect(self._on_torch)
        self._window.snapshotRequested.connect(self._on_camera_snapshot)
        self._window.zoomChanged.connect(self._on_zoom)
        self._window.autoFocusToggled.connect(self._on_autofocus_toggled)
        self._window.focusChanged.connect(self._on_focus_changed)
        self._window.adjustRequested.connect(self._on_adjust_requested)
        self._window.qualityRequested.connect(self._on_quality_requested)

        self._feedback.presenceChanged.connect(self._window.set_presence)
        self._feedback.linkStateChanged.connect(self._window.set_link_state)
        self._feedback.rtcStateChanged.connect(self._window.set_rtc_state)
        self._feedback.mutedChanged.connect(self._on_muted_changed)
        self._feedback.errorRaised.connect(self._on_error)
        self._feedback.driverFinished.connect(self._on_driver_finished)
        self._feedback.addressesReady.connect(self._apply_addresses)
        self._feedback.devicesReady.connect(self._apply_devices)
        self._feedback.cameraDescriptorChanged.connect(self._on_camera_descriptor)
        self._feedback.cameraStatusChanged.connect(self._on_camera_status)
        self._feedback.cameraStatsChanged.connect(self._on_camera_stats)
        self._feedback.cameraVirtualInstalled.connect(self._on_camera_virtual_installed)

    def _build_tray(self, icon_path):
        # Same multi-size icon as the window: the tray draws it at 16px, where a
        # lone 256px pixmap has to be scaled down.
        tray = QSystemTrayIcon(
            _load_icon(icon_path) if icon_path else QIcon(), self._window
        )

        menu = QMenu()
        self._show_action = QAction(self._t("tray_show", "Show Window"), menu)
        self._show_action.triggered.connect(self._show_window)
        menu.addAction(self._show_action)

        self._mute_action = QAction(self._t("tray_mute", "Mute"), menu)
        self._mute_action.triggered.connect(lambda: self._session.toggle_mute(broadcast=True))
        menu.addAction(self._mute_action)

        menu.addSeparator()
        self._quit_action = QAction(self._t("tray_exit", "Quit"), menu)
        self._quit_action.triggered.connect(self._quit)
        menu.addAction(self._quit_action)

        tray.setContextMenu(menu)
        tray.setToolTip("Poros")
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        return tray

    # ------------------------------------------------------------------
    # startup
    # ------------------------------------------------------------------
    def start(self):
        self._window.show()
        self._apply_saved_port()
        self._apply_pin_settings()
        self._window.set_startup_enabled(startup.is_enabled())
        self._apply_close_to_tray()
        # Listen from the start so the host is ready for a phone without the
        # user having to press Connect; it waits for the output device below.
        self._auto_listen_pending = True
        # Enumerating LAN addresses and audio devices shells out to PowerShell
        # and PortAudio and can take seconds. Run on the UI thread right after
        # show(), it blocks the window - and while the window cannot answer the
        # shell's WM_GETICON, Explorer draws its generic placeholder for the
        # taskbar button. Gather off-thread and apply through signals instead.
        threading.Thread(target=self._gather_startup, daemon=True).start()
        threading.Thread(target=self._check_driver, daemon=True).start()

    def _gather_startup(self):
        try:
            port = self._server.port
            addresses = [f"https://{ip}:{port}" for ip in self._server.ips()]
            self._feedback.addressesReady.emit(port, addresses)
        except Exception:
            log.debug("could not enumerate addresses", exc_info=True)

        try:
            devices = list_output_devices()
        except Exception:
            devices = []
        current = find_output_index(self._platform.driver_match_keyword, devices)
        if current is None:
            current = default_output_index(devices)
        self._feedback.devicesReady.emit(devices, current)

    def _apply_addresses(self, port, addresses):
        self._window.set_port(port)
        self._window.set_addresses(addresses)

    def _apply_devices(self, devices, current):
        self._current_device = current
        self._window.set_devices(devices, current)
        if self._auto_listen_pending:
            self._auto_listen_pending = False
            self._on_connect()

    def _apply_saved_port(self):
        saved = self._settings.value("port")
        if saved is None:
            return
        try:
            saved = int(saved)
        except (TypeError, ValueError):
            return
        if saved == self._server.port or not 1024 <= saved <= 65535:
            return
        ok, _ = self._server.restart(saved)
        if not ok:
            QMessageBox.information(
                self._window,
                "Poros",
                self._t("host_port_failed", "Could not use the saved port"),
            )

    def _session_url(self):
        return f"https://127.0.0.1:{self._server.port}"

    def _refresh_addresses(self):
        port = self._server.port
        addresses = [f"https://{ip}:{port}" for ip in self._server.ips()]
        self._apply_addresses(port, addresses)

    def _on_address_selected(self, url):
        self._window.set_selected_address(url)
        png = _make_qr_png(url)
        if png:
            self._window.set_qr(png)

    def _on_port_requested(self, port):
        if port == self._server.port:
            return

        if self._active:
            self._runner.schedule(self._session.stop())

        ok, message = self._server.restart(port)
        if not ok:
            QMessageBox.warning(
                self._window,
                "Poros",
                f"{self._t('host_port_failed', 'Could not use that port')}\n{message}",
            )
            self._window.set_port(self._server.port)
        else:
            self._settings.setValue("port", port)
            self._settings.sync()
            self._refresh_addresses()

        if self._active:
            self._runner.schedule(
                self._session.start(self._session_url(), self._current_device)
            )

    def _check_driver(self):
        try:
            installed = bool(self._platform.is_driver_installed())
        except Exception:
            installed = False

        if installed:
            return

        try:
            success, message = self._platform.install_driver()
        except Exception as exc:
            success, message = False, str(exc)
        self._feedback.driverFinished.emit(success, message)

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def _on_connect(self):
        self._window.set_rtc_state("new")
        self._window.set_active(True)
        self._active = True
        self._runner.schedule(
            self._session.start(self._session_url(), self._current_device)
        )

    def _on_disconnect(self):
        self._active = False
        self._window.set_active(False)
        self._window.set_presence(False)
        self._window.set_rtc_state("new")
        self._runner.schedule(self._session.stop())

    def _on_device_changed(self, index):
        self._current_device = index
        self._session.select_device(index)

    def _on_muted_changed(self, muted):
        self._muted = muted
        self._window.set_muted(muted)
        self._refresh_tray_texts()

    def _refresh_tray_texts(self):
        self._show_action.setText(self._t("tray_show", "Show Window"))
        self._mute_action.setText(
            self._t("tray_unmute", "Unmute") if self._muted else self._t("tray_mute", "Mute")
        )
        self._quit_action.setText(self._t("tray_exit", "Quit"))

    def _on_language_changed(self, code):
        self._translator.load(code)
        self._window.set_language(code)
        self._settings.setValue("language", code)
        self._settings.sync()
        self._refresh_tray_texts()

    def _apply_pin_settings(self):
        saved = self._settings.value("require_pin")
        required = True if saved is None else str(saved).lower() in ("1", "true")
        setter = getattr(self._server, "set_require_pin", None)
        if setter is not None:
            try:
                setter(required)
            except Exception:
                log.debug("could not set the PIN requirement", exc_info=True)

        # A PIN the user typed is reused; otherwise a random one is generated.
        apply_pin = getattr(self._server, "set_pin", None)
        custom = str(self._settings.value("pin") or "").strip()
        if apply_pin is not None:
            try:
                apply_pin(custom)
            except Exception:
                log.debug("could not apply the PIN", exc_info=True)
        self._window.set_pin(getattr(self._server, "pin", "") or "", required)

    def _on_require_pin_changed(self, enabled):
        setter = getattr(self._server, "set_require_pin", None)
        if setter is not None:
            try:
                setter(enabled)
            except Exception:
                log.debug("could not change the PIN requirement", exc_info=True)
        self._settings.setValue("require_pin", bool(enabled))
        self._settings.sync()
        self._window.set_pin(getattr(self._server, "pin", "") or "", bool(enabled))

    def _on_regenerate_pin(self):
        regenerate = getattr(self._server, "regenerate_pin", None)
        if regenerate is not None:
            try:
                regenerate()
            except Exception:
                log.debug("could not regenerate the PIN", exc_info=True)
        # A fresh PIN is meant to be per-run, so drop the remembered one.
        self._settings.setValue("pin", "")
        self._settings.sync()
        self._window.set_pin(
            getattr(self._server, "pin", "") or "",
            getattr(self._server, "require_pin", True),
        )

    def _apply_close_to_tray(self):
        saved = self._settings.value("close_to_tray")
        enabled = True if saved is None else str(saved).lower() in ("1", "true")
        self._window.set_close_to_tray(enabled)

    def _on_close_to_tray_changed(self, enabled):
        self._settings.setValue("close_to_tray", bool(enabled))
        self._settings.sync()

    def _on_startup_changed(self, enabled):
        if not startup.set_enabled(enabled):
            # Could not write the registry: put the checkbox back to reality.
            self._window.set_startup_enabled(startup.is_enabled())

    def _on_pin_changed(self, value):
        apply_pin = getattr(self._server, "set_pin", None)
        if apply_pin is not None:
            try:
                apply_pin(value)
            except Exception:
                log.debug("could not set the PIN", exc_info=True)
        self._settings.setValue("pin", str(value).strip())
        self._settings.sync()
        self._window.set_pin(
            getattr(self._server, "pin", "") or "",
            getattr(self._server, "require_pin", True),
        )

    def _on_error(self, message):
        QMessageBox.warning(self._window, "Poros", message)

    def _on_driver_finished(self, success, message):
        if success:
            warning = self._platform.get_post_install_warning()
            if warning:
                QMessageBox.information(
                    self._window, self._t("reminder_title", "\u26a0\ufe0f Important: Restore Audio"), warning
                )
        else:
            QMessageBox.warning(
                self._window, self._t("install_title_fail", "Installation Failed"), message or ""
            )

    # ------------------------------------------------------------------
    # camera
    # ------------------------------------------------------------------
    def _camera_resolutions(self):
        if not self._camera_descriptor:
            return []
        result = []
        for entry in self._camera_descriptor.get("resolutions") or []:
            try:
                result.append((int(entry[0]), int(entry[1])))
            except Exception:
                continue
        return result

    def _on_camera_descriptor(self, descriptor):
        self._camera_descriptor = descriptor if isinstance(descriptor, dict) else None
        available = bool(self._camera_descriptor)
        name = str(self._camera_descriptor.get("name", "")) if available else ""
        lens = str(self._camera_descriptor.get("lens", "back")) if available else "back"
        self._camera_back = lens != "front"
        self._window.set_camera_available(available, name)

        if not available:
            self._stop_camera()

    def _on_camera_status(self, state, detail=""):
        # The receiver reports how the link is doing; show it in the preview
        # while there is no picture yet, and keep hard errors visible.
        if state == "connecting":
            self._window.set_camera_placeholder(
                self._t("camera_connecting", "Connecting to the camera...")
            )
        elif state == "reconnecting":
            self._window.set_camera_placeholder(
                self._t("camera_reconnecting", "Reconnecting...")
            )
        elif state == "error":
            self._window.set_camera_placeholder(
                f"{self._t('camera_error', 'Camera error')}: {detail}" if detail
                else self._t("camera_error", "Camera error")
            )
        elif state == "stopped" and not self._camera_streaming:
            self._window.set_camera_placeholder(
                self._t("camera_waiting", "Waiting for the phone camera...")
            )

    def _on_camera_toggle(self):
        if self._camera_streaming:
            self._stop_camera()
        else:
            self._on_camera_start()

    def _on_camera_start(self):
        if not video.library_available():
            QMessageBox.warning(
                self._window,
                "Poros",
                self._t("camera_unavailable", "The virtual camera component is missing."),
            )
            return
        if not self._camera_descriptor:
            QMessageBox.information(
                self._window,
                "Poros",
                self._t("camera_none", "Turn the camera on from the phone first."),
            )
            return
        if not video.is_virtual_camera_installed():
            self._pending_camera_start = True
            threading.Thread(target=self._install_virtual_camera_worker, daemon=True).start()
            return
        self._begin_camera()

    def _virtual_camera_size(self):
        width, height = self._camera_size
        if self._rotation in (90, 270):
            return height, width
        return width, height

    def _begin_camera(self):
        settings = self._camera_settings
        width, height = int(settings["width"]), int(settings["height"])

        url = str((self._camera_descriptor or {}).get("url") or "")
        host = urlsplit(url).hostname or ""
        if not url or host in ("127.0.0.1", "localhost", "::1"):
            # The phone handed over an address only it can reach. Connecting
            # would just time out, so say what is actually wrong.
            self._window.set_camera_placeholder(
                self._t(
                    "camera_loopback",
                    "The phone did not report a reachable address - check that it is on the same Wi-Fi.",
                )
            )
            return

        self._camera_size = (width, height)
        try:
            self._virtual_cam.open(*self._virtual_camera_size())
        except Exception as exc:
            QMessageBox.warning(self._window, "Poros", str(exc))
            return

        self._receiver.start(
            url, width, height, settings.get("transport", "tcp"), self._rotation
        )
        self._session.start_camera(width, height, int(settings["fps"]))
        self._apply_camera_quality()

        self._camera_streaming = True
        self._window.set_camera_streaming(True)

    def _apply_camera_quality(self):
        settings = self._camera_settings
        self._session.send_camera_command(
            "codec", "h265" if settings.get("codec") == "h265" else "h264"
        )
        if settings.get("adaptive"):
            self._session.send_camera_command(
                "adaptive",
                {"min": int(settings["min_bitrate"]), "max": int(settings["max_bitrate"])},
            )
        else:
            self._session.send_camera_command("bitrate", int(settings["bitrate"]))
        # Focus is driven from the main window, but re-apply it here so a fresh
        # stream starts with the mode the user already chose.
        self._session.send_camera_command("focus", 0 if self._autofocus else 1)
        if not self._autofocus:
            self._session.send_camera_command("focus_distance", self._focus_distance)

    def _stop_camera(self):
        was_streaming = self._camera_streaming
        self._camera_streaming = False
        self._receiver.stop()
        self._virtual_cam.close()
        with self._frame_lock:
            self._latest_frame = None
        self._window.set_camera_streaming(False)
        if was_streaming:
            self._session.stop_camera()

    def _on_camera_command(self, op, value):
        self._session.send_camera_command(op, value)

    # ---- translate the on-screen controls into phone commands ---------
    def _on_rotate(self, degrees):
        self._rotation = (self._rotation + int(degrees)) % 360
        # The receiver rotates the frames itself, so only the virtual camera's
        # container has to be re-made for the new orientation.
        self._receiver.set_rotation(self._rotation)
        self._resize_virtual_camera()

    def _resize_virtual_camera(self):
        if not self._camera_streaming:
            return
        wanted = self._virtual_camera_size()
        if wanted == self._virtual_cam.size:
            return
        try:
            self._virtual_cam.open(*wanted)
        except Exception:
            log.debug("could not resize the virtual camera", exc_info=True)

    def _on_flip(self, axis):
        self._session.send_camera_command("flip", axis)

    def _on_swap(self):
        self._camera_back = not self._camera_back
        self._session.send_camera_command("swap", "back" if self._camera_back else "front")

    def _on_torch(self, enabled):
        self._session.send_camera_command("torch", bool(enabled))

    def _on_zoom(self, value):
        self._session.send_camera_command("zoom", float(value))

    def _on_autofocus_toggled(self, enabled):
        self._autofocus = bool(enabled)
        # 0 = continuous autofocus, 1 = fixed/manual.
        self._session.send_camera_command("focus", 0 if self._autofocus else 1)

    def _on_focus_changed(self, value):
        self._focus_distance = int(value)
        self._session.send_camera_command("focus_distance", int(value))

    def _on_quality_requested(self):
        if self._quality_dialog is None:
            self._quality_dialog = QualityDialog(self._t, self._window)
            self._quality_dialog.applied.connect(self._on_quality_applied)
        self._quality_dialog.set_resolutions(self._camera_resolutions())
        self._quality_dialog.set_state(self._camera_settings)
        self._quality_dialog.show()
        self._quality_dialog.raise_()
        self._quality_dialog.activateWindow()

    def _on_quality_applied(self, settings):
        previous = dict(self._camera_settings)
        self._camera_settings.update(settings)
        if not self._camera_streaming:
            return

        resolution_changed = (
            previous.get("width"), previous.get("height"), previous.get("fps")
        ) != (settings["width"], settings["height"], settings["fps"])
        if resolution_changed:
            # The encoder has to be reconfigured, which means a short restart.
            self._stop_camera()
            self._on_camera_start()
        else:
            self._apply_camera_quality()

    def _on_adjust_requested(self):
        if self._adjust_dialog is None:
            self._adjust_dialog = AdjustDialog(self._t, self._window)
            self._adjust_dialog.correctionChanged.connect(
                lambda name, value: self._session.send_camera_command(
                    "filter_param", {"name": name, "value": value}
                )
            )
            self._adjust_dialog.effectChanged.connect(
                lambda name: self._session.send_camera_command("filter_effect", name)
            )
            self._adjust_dialog.resetRequested.connect(
                lambda: self._session.send_camera_command("filter_reset", None)
            )
        self._adjust_dialog.show()
        self._adjust_dialog.raise_()
        self._adjust_dialog.activateWindow()

    def _on_camera_snapshot(self):
        frame = self._take_frame()
        if frame is None:
            return
        path = self._snapshot_path()
        height, width = frame.shape[:2]
        image = QImage(frame.data, width, height, 3 * width, QImage.Format_BGR888).copy()
        if image.save(path, "JPEG", 92):
            QMessageBox.information(
                self._window,
                "Poros",
                self._t("camera_snapshot_saved", "Snapshot saved to {path}").replace(
                    "{path}", path
                ),
            )

    def _snapshot_path(self):
        folder = os.path.join(os.path.expanduser("~"), "Pictures", "Poros")
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception:
            folder = os.path.expanduser("~")
        stamp = time.strftime("%Y%m%d_%H%M%S")
        return os.path.join(folder, f"Poros_{stamp}.jpg")

    def _install_virtual_camera_worker(self):
        try:
            ok, message = video.install_virtual_camera()
        except Exception as exc:
            ok, message = False, str(exc)
        installed = video.is_virtual_camera_installed()
        self._feedback.cameraVirtualInstalled.emit(
            installed, "" if installed else (message or self._t("camera_unavailable", ""))
        )

    def _on_camera_virtual_installed(self, installed, message):
        if message:
            QMessageBox.warning(self._window, "Poros", message)

        if installed and self._pending_camera_start:
            self._pending_camera_start = False
            self._begin_camera()
        elif not installed:
            self._pending_camera_start = False

    def _on_video_frame(self, frame):
        """Receiver thread: fan the frame out to the preview and the virtual camera."""
        with self._frame_lock:
            self._latest_frame = frame
        try:
            # The virtual camera copies into shared memory itself, so hand it the
            # array directly rather than materialising a second copy here.
            self._virtual_cam.send(frame)
        except Exception:
            log.debug("could not push a video frame", exc_info=True)

    def _take_frame(self):
        with self._frame_lock:
            return self._latest_frame

    def _on_video_state(self, state, detail=""):
        """Receiver thread: hop to the UI thread through the feedback bridge."""
        self._feedback.set_camera_status(state, detail)

    def _on_video_stats(self, sample):
        """Receiver thread: hop to the UI thread through the feedback bridge."""
        self._feedback.set_camera_stats(sample)

    def _on_camera_stats(self, sample):
        self._window.set_camera_stats(sample)

    def _on_about(self):
        QMessageBox.about(
            self._window,
            "Poros",
            f"Poros Desktop {self._version}\n\n"
            "WebRTC over LAN - no cloud, no account.",
        )

    # ------------------------------------------------------------------
    # tray / window
    # ------------------------------------------------------------------
    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._show_window()

    def _show_window(self):
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    def _on_window_hidden(self):
        if not self._hint_shown:
            self._hint_shown = True
            self._tray.showMessage(
                "Poros", self._t("tray_hint", "Poros is still running in the tray")
            )

    def _quit(self):
        self._window.allow_close = True
        try:
            self._receiver.stop()
            self._virtual_cam.close()
        except Exception:
            log.debug("could not stop the camera", exc_info=True)
        try:
            self._runner.schedule(self._session.stop())
        except Exception:
            pass
        self._runner.stop()
        self._tray.hide()
        self._qapp.quit()


def run_desktop(platform, version, webui_dir, icon_path=None, server=None):
    # Before QApplication, so the window it creates already belongs to this
    # taskbar identity. See the helper for why this is needed.
    _apply_windows_taskbar_identity()

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setApplicationName("Poros")
    app.setQuitOnLastWindowClosed(False)

    if icon_path:
        icon = _load_icon(icon_path)
        if not icon.isNull():
            app.setWindowIcon(icon)

    style = _style_path()
    if style:
        try:
            with open(style, "r", encoding="utf-8") as handle:
                app.setStyleSheet(handle.read())
        except Exception:
            log.debug("could not load stylesheet")

    controller = DesktopApp(
        app, platform, version, webui_dir, icon_path, server
    )
    controller.start()
    return app.exec()
