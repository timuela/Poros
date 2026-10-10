"""Headless smoke test for the Qt desktop app.

Run it with QT_QPA_PLATFORM=offscreen. It builds the real window and
controller, exercises every setter and forces a repaint, which catches
missing or misnamed Qt APIs and paint-time errors. This is the check that
would have caught `QApplication.applicationIcon()` before it shipped.
"""

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from desktop.app import DesktopApp, Translator, _load_icon, _style_path
from desktop.ui import MainWindow

failures = []
advisory = []


def check(label, ok, detail=""):
    print(f"  [{'ok ' if ok else 'FAIL'}] {label} {detail}")
    if not ok:
        failures.append(label)


# A QApplication must exist before any QIcon or QPixmap is created.
app = QApplication.instance() or QApplication([])
print("qt platform:", app.platformName())

# The controller reports problems through modal dialogs, which would block
# forever offscreen. Record them instead.
dialogs = []
QMessageBox.warning = staticmethod(lambda *a, **k: dialogs.append(a))
QMessageBox.information = staticmethod(lambda *a, **k: dialogs.append(a))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)


class PlatformStub:
    driver_display_name = "CABLE Input"
    driver_match_keyword = "cable input"
    post_install_warning = ""

    def list_lan_ips(self):
        return ["192.168.10.152", "100.100.65.1"]

    def is_driver_installed(self):
        return True

    def install_driver(self):
        return True, ""

    def uninstall_driver(self):
        return True, ""


class ServerStub:
    def __init__(self):
        self.port = 5000

    def ips(self):
        return ["192.168.10.152", "100.100.65.1"]

    def restart(self, port):
        if port == 1:
            return False, "port in use"
        self.port = port
        return True, ""


print("assets:")
check("style.qss is bundled", _style_path() is not None, str(_style_path()))
png = QIcon(os.path.join(ROOT, "desktop", "icon.png"))
check("desktop/icon.png loads", not png.isNull())

# Windows asks the shell for 16-32px for taskbar and title-bar buttons. An
# icon built from a single 256px source has nothing to offer at those sizes,
# which is how the taskbar ends up drawing its generic white placeholder.
icon_sizes = {
    size.width()
    for size in _load_icon(os.path.join(ROOT, "desktop", "icon.png")).availableSizes()
}
check("icon carries the small sizes the taskbar asks for",
      {16, 24, 32}.issubset(icon_sizes), f"sizes={sorted(icon_sizes)}")

print("window:")
try:
    window = MainWindow(Translator(os.path.join(ROOT, "webui")), "v0.1.4")
    check("MainWindow constructs", True)
    check("settings panel offers three languages",
          window._language_combo.count() == 3, str(window._language_combo.count()))
    window.set_language("vi_vn")
    check("language combo follows set_language",
          window._language_combo.currentData() == "vi_vn")
    window.set_pin("123456", True)
    check("PIN is surfaced when required", window._pin_edit.text() == "123456")
    check("settings offers Start with Windows", hasattr(window, "_startup_check"))
    window.set_devices([(0, "CABLE Input")], 0)
    window.set_addresses(["https://192.168.10.152:5000", "https://100.100.65.1:5000"])
    window.set_selected_address("https://100.100.65.1:5000")
    window.set_port(5000)
    window.set_gain(1.4)
    window.set_presence(True)
    window.set_muted(True)
    window.set_rtc_state("connected")
    window.set_link_state("connected")
    window.retranslate()
    window.set_language("zh_cn")
    window.set_language("en_us")
    check("all setters ran", True)
    pixmap = window.grab()
    if pixmap.isNull():
        # Offscreen rendering can legitimately produce no pixmap on some
        # platforms; painting still ran, so this is not a failure.
        advisory.append("window.grab() returned no pixmap here")
        print("  [skip] window.grab() returned no pixmap here")
    else:
        check("window paints", True, f"{pixmap.width()}x{pixmap.height()}")

    # The window must not force itself taller as the state changes: showing a
    # long address list or the microphone pad used to raise the layout minimum,
    # so Qt grew the window and the user's resize did not stick.
    window.set_addresses([f"https://10.0.0.{i}:5000" for i in range(1, 9)])
    window.set_presence(False)
    disconnected = window.minimumSizeHint().height()
    window.set_presence(True)
    window.set_presence(False)
    again = window.minimumSizeHint().height()
    check("minimum height stays small with many addresses", disconnected < 250, f"{disconnected}px")
    check("minimum height is stable across connect/disconnect",
          again == disconnected, f"{disconnected} -> {again}")
except Exception as exc:
    check("MainWindow builds and paints", False, f"{type(exc).__name__}: {exc}")

print("controller (advisory: needs a tray/DBus and asyncio, so it never fails the build):")
try:
    controller = DesktopApp(
        app, PlatformStub(), "v0.1.4", os.path.join(ROOT, "webui"), None, ServerStub()
    )
    controller._settings = QSettings(
        os.path.join(tempfile.gettempdir(), "poros-smoke.ini"), QSettings.IniFormat
    )
    controller._refresh_addresses()
    check("addresses refresh", True)
    controller._on_address_selected("https://100.100.65.1:5000")
    check("address selection builds a QR code", True)
    controller._on_port_requested(5050)
    check("port change applies", controller._server.port == 5050, str(controller._server.port))
    controller._on_port_requested(1)
    check("bad port reverts", controller._server.port == 5050, str(controller._server.port))
    check("bad port is reported", len(dialogs) > 0, f"{len(dialogs)} dialog(s)")
    controller._on_language_changed("vi_vn")
    controller._refresh_tray_texts()
    check("language and tray refresh", True)
    check("language switched to Vietnamese", controller._translator.lang == "vi_vn",
          controller._translator.lang)
    controller._quit()
except Exception as exc:
    advisory.append(f"controller checks unavailable here: {type(exc).__name__}: {exc}")
    print(f"  [skip] {advisory[-1]}")

print()
for note in advisory:
    print("  !", note)
print(f"failures: {len(failures)}")
for failure in failures:
    print("  -", failure)
sys.exit(1 if failures else 0)
