import math
import os
import sys

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRegularExpression,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QImage,
    QIntValidator,
    QPainter,
    QPen,
    QPixmap,
    QRegularExpressionValidator,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

DOT_IDLE = "#888888"
DOT_OK = "#4CAF50"
DOT_WARN = "#FF9800"
DOT_ERROR = "#FF5252"

ICON_FILE_OFF = "icon-volume-off.png"
ICON_FILE_UP = "icon-volume-up.png"

# The two round buttons sit side by side, so keep them compact and leave the
# window short enough that everything (including Disconnect) fits unscrolled.
BUTTON_DIAMETER = 76
BUTTON_WIDGET_SIZE = 104
CAMERA_GLYPH_SIZE = 38
RING_MAX_SCALE = 1.4
ICON_PIXEL_SIZE = 34

BUTTON_IDLE_BG = QColor(0x2A, 0x2A, 0x2A)
BUTTON_IDLE_FG = QColor(0x8A, 0x8A, 0x8A)
BUTTON_ACTIVE_BG = QColor(0x42, 0x85, 0xF4)
BUTTON_ACTIVE_FG = QColor(0xFF, 0xFF, 0xFF)
BUTTON_MUTED_BG = QColor(0xFF, 0xB3, 0xAE)
BUTTON_MUTED_FG = QColor(0x4A, 0x00, 0x05)

SETTINGS_PANEL_WIDTH = 320

# Shared geometry for the PIN/Port rows, so their labels and fields line up.
FIELD_STYLE = "font-family: monospace; font-size: 15px;"
FIELD_WIDTH = 88
LABEL_WIDTH = 32

_pixmap_cache = {}
_tinted_cache = {}


def _load_pixmap(filename):
    if filename in _pixmap_cache:
        return _pixmap_cache[filename]

    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, filename),
        os.path.join(getattr(sys, "_MEIPASS", ""), "desktop", filename),
    ]

    pixmap = None
    for path in candidates:
        if path and os.path.exists(path):
            candidate = QPixmap(path)
            if not candidate.isNull():
                pixmap = candidate
                break

    _pixmap_cache[filename] = pixmap
    return pixmap


def _tinted_pixmap(filename, color):
    """Recolour a white glyph on a transparent background by keeping its alpha."""
    key = (filename, color.rgba())
    if key in _tinted_cache:
        return _tinted_cache[key]

    source = _load_pixmap(filename)
    tinted = None
    if source is not None:
        tinted = QPixmap(source.size())
        tinted.fill(Qt.transparent)
        painter = QPainter(tinted)
        painter.drawPixmap(0, 0, source)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), color)
        painter.end()

    _tinted_cache[key] = tinted
    return tinted


def _normalise_level(rms):
    """Map a linear RMS value onto 0..1 using a dB curve, so it does not saturate."""
    if rms <= 0.0:
        return 0.0
    db = 20.0 * math.log10(rms)
    return max(0.0, min(1.0, (db + 54.0) / 44.0))


_icon_family = None
_icon_fonts = {}


def _resource_path(name):
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, name),
        os.path.join(getattr(sys, "_MEIPASS", ""), "desktop", name),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def material_icon_family():
    """Family name of the bundled Material Icons font ("" if unavailable)."""
    global _icon_family
    if _icon_family is None:
        _icon_family = ""
        path = _resource_path("MaterialIcons-Regular.ttf")
        if path:
            font_id = QFontDatabase.addApplicationFont(path)
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    _icon_family = families[0]
        if not _icon_family:
            print("[Poros] Material Icons font could not be loaded")
    return _icon_family


def _icon_font(pixel_size):
    size = int(pixel_size)
    font = _icon_fonts.get(size)
    if font is None:
        font = QFont(material_icon_family() or "Segoe UI")
        font.setPixelSize(size)
        _icon_fonts[size] = font
    return font


def _draw_icon(painter, ligature, rect, color, pixel_size=22):
    """Draw a Material Icons glyph, centred in ``rect``.

    The font turns the ligature name ("rotate_left") into the glyph, so the
    icons come from the real icon set rather than being drawn by hand.
    """
    painter.setFont(_icon_font(pixel_size))
    painter.setPen(color)
    painter.drawText(rect, Qt.AlignCenter, ligature)


class IconButton(QPushButton):
    """Round button showing a Material Icons glyph."""

    def __init__(self, kind, tooltip="", checkable=False, diameter=40,
                 glyph_size=22, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._diameter = diameter
        self._glyph_size = glyph_size
        self.setFixedSize(diameter, diameter)
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(checkable)
        self.setToolTip(tooltip)
        self.setFlat(True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        radius = self._diameter / 2.0
        centre = QPointF(self.width() / 2.0, self.height() / 2.0)

        if self.isChecked():
            background = BUTTON_ACTIVE_BG
            foreground = BUTTON_ACTIVE_FG
        elif self.underMouse() and self.isEnabled():
            background = QColor(0x3A, 0x3A, 0x3A)
            foreground = QColor(0xE6, 0xE6, 0xE6)
        else:
            background = BUTTON_IDLE_BG
            foreground = BUTTON_IDLE_FG
        if not self.isEnabled():
            foreground = QColor(0x5A, 0x5A, 0x5A)

        painter.setPen(Qt.NoPen)
        painter.setBrush(background)
        painter.drawEllipse(centre, radius, radius)

        _draw_icon(painter, self._kind, self.rect(), foreground, self._glyph_size)


class _PreviewArea(QWidget):
    """The inline video surface, with the live stream stats over it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.setStyleSheet("background: #000000; border-radius: 10px;")

        self._image = QLabel(self)
        self._image.setAlignment(Qt.AlignCenter)
        self._image.setStyleSheet("background: transparent;")
        self._placeholder = ""

        self._stats = QLabel(self)
        self._stats.setStyleSheet(
            "background: rgba(0, 0, 0, 160); color: #FFFFFF; padding: 3px 8px;"
            " border-radius: 6px; font-family: monospace; font-size: 11px;"
        )
        self._stats.hide()

        self._frame_source = None
        self._streaming = False
        self._has_frame = False
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._pull)

    def set_placeholder(self, text):
        self._placeholder = text
        if not self._has_frame:
            self._image.setText(text)

    def set_frame_source(self, source):
        self._frame_source = source

    def set_streaming(self, streaming):
        if streaming == self._streaming:
            return
        self._streaming = streaming
        self._has_frame = False
        if streaming:
            self._timer.start()
            self._image.clear()
            self._image.setText(self._placeholder)
        else:
            self._timer.stop()
            self._image.clear()
            self._image.setText(self._placeholder)
            self._stats.hide()

    def set_stats(self, sample):
        if not sample:
            self._stats.hide()
            return
        width = int(sample.get("width", 0) or 0)
        height = int(sample.get("height", 0) or 0)
        latency = float(sample.get("latency", 0.0) or 0.0)
        text = (
            f"{width}x{height} \u00b7 {float(sample.get('fps', 0.0)):.0f} fps"
            f" \u00b7 {float(sample.get('mbps', 0.0)):.1f} Mbps"
            f" \u00b7 {latency:.2f} s"
        )
        dropped = int(sample.get("dropped", 0) or 0)
        if dropped:
            text += f" \u00b7 {dropped} dropped"
        self._stats.setText(text)
        self._stats.adjustSize()
        self._stats.show()
        self._position_stats()

    def _position_stats(self):
        self._stats.move(10, 10)

    def _pull(self):
        if not self._streaming or self._frame_source is None:
            return
        try:
            frame = self._frame_source()
        except Exception:
            frame = None
        if frame is None:
            return

        height, width = frame.shape[:2]
        image = QImage(frame.data, width, height, 3 * width, QImage.Format_BGR888)
        target = self._image.size()
        if target.width() < 4 or target.height() < 4:
            return
        scaled = image.scaled(target, Qt.KeepAspectRatio, Qt.FastTransformation)
        if not self._has_frame:
            self._has_frame = True
            self._image.setText("")
        self._image.setPixmap(QPixmap.fromImage(scaled))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._image.setGeometry(self.rect())
        self._position_stats()


class _Scrim(QWidget):
    """Semi-transparent overlay that closes the settings panel when clicked."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: rgba(0, 0, 0, 150);")

    def mousePressEvent(self, event):
        self.clicked.emit()


class _LanguageCombo(QComboBox):
    """Combo box whose drop-down chevron is painted by hand.

    Styling QComboBox::drop-down in the stylesheet suppresses the native arrow,
    so draw our own rather than ship an image asset.
    """

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor("#9a9a9a"))
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        cx = self.width() - 16.0
        cy = self.height() / 2.0
        painter.drawLine(QPointF(cx - 4.5, cy - 2.0), QPointF(cx, cy + 2.5))
        painter.drawLine(QPointF(cx, cy + 2.5), QPointF(cx + 4.5, cy - 2.0))


class _DeviceCombo(QComboBox):
    """Combo box whose drop-down is wide enough for the longest device name.

    The box itself stays narrow (see setMinimumContentsLength) so a long name
    cannot force the window wider, but the list it opens has to show the names
    in full: several of them share long prefixes, and a clipped one is
    impossible to tell from another. Only the pop-up is resized, so the combo's
    own size hint - and the window - are unaffected.
    """

    def showPopup(self):
        super().showPopup()

        widest = 0
        metrics = QFontMetrics(self.view().font())
        for row in range(self.count()):
            widest = max(widest, metrics.horizontalAdvance(self.itemText(row)))
        if widest == 0:
            return

        popup = self.view().window()
        if popup is self:
            return

        # Room for the item padding, the scroll bar and the pop-up frame.
        wanted = widest + 56
        screen = QApplication.primaryScreen()
        geometry = screen.availableGeometry() if screen is not None else None
        if geometry is not None:
            wanted = min(wanted, geometry.width() - 40)
        if popup.width() >= wanted:
            return

        popup.resize(wanted, popup.height())
        # Keep it on screen now that it is wider than the combo.
        if geometry is not None and popup.x() + wanted > geometry.right():
            popup.move(max(geometry.left(), geometry.right() - wanted), popup.y())


class CameraToggle(QWidget):
    """Round camera button, the same size and behaviour as the mic button."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(BUTTON_WIDGET_SIZE, BUTTON_WIDGET_SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self._on = False
        self._armed = False  # the mic session is up, so the camera can run

    def set_state(self, on, armed):
        if (on, armed) == (self._on, self._armed):
            return
        self._on = bool(on)
        self._armed = bool(armed)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._armed:
            self.clicked.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if self._on:
            background, foreground = BUTTON_ACTIVE_BG, BUTTON_ACTIVE_FG
        else:
            background, foreground = BUTTON_IDLE_BG, BUTTON_IDLE_FG
        if not self._armed:
            foreground = QColor(0x5A, 0x5A, 0x5A)

        centre = QPointF(self.width() / 2.0, self.height() / 2.0)
        painter.setPen(Qt.NoPen)
        painter.setBrush(background)
        painter.drawEllipse(centre, BUTTON_DIAMETER / 2.0, BUTTON_DIAMETER / 2.0)

        _draw_icon(
            painter,
            "videocam" if self._on else "videocam_off",
            self.rect(),
            foreground,
            CAMERA_GLYPH_SIZE,
        )


class MicButton(QWidget):
    """Round toggle that mirrors the web UI's speaker button."""

    clicked = Signal()

    def __init__(self, level_provider=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(BUTTON_WIDGET_SIZE, BUTTON_WIDGET_SIZE)
        self.setCursor(Qt.PointingHandCursor)

        self._level_provider = level_provider
        self._state = "idle"
        self._display = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60 fps, like requestAnimationFrame
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_state(self, state):
        if state != self._state:
            self._state = state
            if state != "active":
                self._display = 0.0
            self.update()

    def set_level_provider(self, provider):
        self._level_provider = provider

    def _tick(self):
        if self._state != "active" and self._display <= 0.002:
            return

        target = 0.0
        if self._state == "active" and self._level_provider is not None:
            try:
                target = _normalise_level(float(self._level_provider()))
            except Exception:
                target = 0.0

        # Fast attack, slow release: glides instead of snapping to full size.
        rate = 0.26 if target > self._display else 0.06
        self._display += (target - self._display) * rate
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        if self._state == "muted":
            button_bg, icon_fg, icon_file = BUTTON_MUTED_BG, BUTTON_MUTED_FG, ICON_FILE_OFF
        elif self._state == "active":
            button_bg, icon_fg, icon_file = BUTTON_ACTIVE_BG, BUTTON_ACTIVE_FG, ICON_FILE_UP
        else:
            button_bg, icon_fg, icon_file = BUTTON_IDLE_BG, BUTTON_IDLE_FG, ICON_FILE_OFF

        centre = QPointF(self.width() / 2.0, self.height() / 2.0)
        button_radius = BUTTON_DIAMETER / 2.0

        # Ring first, so it sits behind the button and grows evenly outwards.
        if self._display > 0.002:
            ring = QColor(button_bg)
            ring.setAlphaF(min(0.55, 0.12 + self._display * 0.43))
            ring_radius = button_radius * (1.0 + self._display * (RING_MAX_SCALE - 1.0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(ring)
            painter.drawEllipse(centre, ring_radius, ring_radius)

        painter.setPen(Qt.NoPen)
        painter.setBrush(button_bg)
        painter.drawEllipse(centre, button_radius, button_radius)

        pixmap = _tinted_pixmap(icon_file, icon_fg)
        if pixmap is not None:
            ratio = self.devicePixelRatioF() or 1.0
            target = QSize(int(ICON_PIXEL_SIZE * ratio), int(ICON_PIXEL_SIZE * ratio))
            scaled = pixmap.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            scaled.setDevicePixelRatio(ratio)
            width = scaled.width() / ratio
            height = scaled.height() / ratio
            painter.drawPixmap(
                QPointF(centre.x() - width / 2.0, centre.y() - height / 2.0), scaled
            )


class MainWindow(QMainWindow):
    connectRequested = Signal()
    disconnectRequested = Signal()
    muteToggled = Signal()
    gainChanged = Signal(float)
    deviceChanged = Signal(int)
    aboutRequested = Signal()
    languageChanged = Signal(str)
    requirePinChanged = Signal(bool)
    regeneratePinRequested = Signal()
    pinChanged = Signal(str)
    startupChanged = Signal(bool)
    closeToTrayChanged = Signal(bool)
    quitRequested = Signal()
    installReminderAcknowledged = Signal()
    addressSelected = Signal(str)
    portChangeRequested = Signal(int)
    cameraRequested = Signal()
    cameraToggleRequested = Signal()
    rotateRequested = Signal(int)
    flipRequested = Signal(str)
    swapRequested = Signal()
    torchToggled = Signal(bool)
    snapshotRequested = Signal()
    zoomChanged = Signal(float)
    adjustRequested = Signal()
    qualityRequested = Signal()
    autoFocusToggled = Signal(bool)
    focusChanged = Signal(int)

    def __init__(self, t, version, language="en_us"):
        super().__init__()
        self._t = t
        self._version = version
        self._language = language
        # Closing hides to the tray by default; the settings panel can turn that
        # off, in which case closing the window quits the app.
        self.close_to_tray = True
        self._link_up = False
        self._presence = False
        self._rtc_state = "new"
        self._muted = False
        self._active = False
        self._level_provider = None
        self._settings_open = False
        self._pin = ""
        self._pin_required = True
        self._camera_available = False
        self._camera_streaming = False
        self._zoom = 1.0
        self._build()

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _build(self):
        self.setWindowTitle("Poros Desktop")
        self.resize(520, 820)
        self.setWindowIcon(QApplication.windowIcon())

        content = QWidget()
        content.setObjectName("centralWidget")
        root = QVBoxLayout(content)
        root.setContentsMargins(16, 10, 16, 10)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("\U0001F399  Poros")
        title.setObjectName("headerTitle")
        header.addWidget(title)

        self._version_label = QLabel(self._version)
        self._version_label.setObjectName("versionLabel")
        header.addWidget(self._version_label)
        header.addStretch(1)

        self._settings_button = QPushButton("\u2630")
        self._settings_button.setObjectName("flatButton")
        self._settings_button.setFixedWidth(44)
        self._settings_button.setToolTip(self._t("settings_title", "Settings"))
        self._settings_button.clicked.connect(
            lambda: self._set_settings_open(not self._settings_open)
        )
        header.addWidget(self._settings_button)

        root.addLayout(header)

        # ---- status card ------------------------------------------------
        card = QFrame()
        card.setObjectName("card")
        # Keep the status card at its natural height: without a stretch below it,
        # any spare vertical space would otherwise inflate this card.
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(20, 14, 20, 14)

        status_box = QVBoxLayout()
        status_box.setSpacing(6)
        self._status_title = QLabel(self._t("status_label", "Mobile Connection"))
        self._status_title.setObjectName("statusTitle")
        status_box.addWidget(self._status_title)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self._dot = QLabel()
        self._dot.setFixedSize(10, 10)
        status_row.addWidget(self._dot)
        self._status_text = QLabel("")
        self._status_text.setObjectName("statusText")
        status_row.addWidget(self._status_text)
        status_row.addStretch(1)
        status_box.addLayout(status_row)

        card_layout.addLayout(status_box)
        card_layout.addStretch(1)
        root.addWidget(card)

        # ---- inline video + camera controls -----------------------------
        self._video_panel = QFrame()
        self._video_panel.setObjectName("card")
        video_layout = QVBoxLayout(self._video_panel)
        video_layout.setContentsMargins(10, 10, 10, 10)
        video_layout.setSpacing(8)

        self._preview_area = _PreviewArea()
        self._preview_area.set_placeholder(
            self._t("camera_waiting", "Waiting for the phone camera...")
        )
        video_layout.addWidget(self._preview_area, 1)

        row_one = QHBoxLayout()
        row_one.setSpacing(6)
        self._rotate_left_button = IconButton(
            "rotate_left", self._t("camera_rotate_left", "Rotate left")
        )
        self._rotate_left_button.clicked.connect(lambda: self.rotateRequested.emit(-90))
        self._rotate_right_button = IconButton(
            "rotate_right", self._t("camera_rotate_right", "Rotate right")
        )
        self._rotate_right_button.clicked.connect(lambda: self.rotateRequested.emit(90))
        self._flip_h_button = IconButton(
            "flip", self._t("camera_flip_h", "Flip horizontally")
        )
        self._flip_h_button.clicked.connect(lambda: self.flipRequested.emit("horizontal"))
        self._flip_v_button = IconButton(
            "swap_vert", self._t("camera_flip_v", "Flip vertically")
        )
        self._flip_v_button.clicked.connect(lambda: self.flipRequested.emit("vertical"))
        for button in (
            self._rotate_left_button,
            self._rotate_right_button,
            self._flip_h_button,
            self._flip_v_button,
        ):
            row_one.addWidget(button)
        row_one.addStretch(1)

        self._zoom_out_button = IconButton("zoom_out", self._t("camera_zoom_out", "Zoom out"))
        self._zoom_out_button.clicked.connect(lambda: self._nudge_zoom(-0.5))
        row_one.addWidget(self._zoom_out_button)
        self._zoom_label = QLabel("1.0x")
        self._zoom_label.setObjectName("gainValue")
        self._zoom_label.setAlignment(Qt.AlignCenter)
        self._zoom_label.setFixedWidth(46)
        row_one.addWidget(self._zoom_label)
        self._zoom_in_button = IconButton("zoom_in", self._t("camera_zoom_in", "Zoom in"))
        self._zoom_in_button.clicked.connect(lambda: self._nudge_zoom(0.5))
        row_one.addWidget(self._zoom_in_button)
        video_layout.addLayout(row_one)

        row_two = QHBoxLayout()
        row_two.setSpacing(6)
        self._torch_button = IconButton(
            "flash_on", self._t("camera_torch", "Torch"), checkable=True
        )
        self._torch_button.toggled.connect(self.torchToggled.emit)
        self._swap_button = IconButton("cameraswitch", self._t("camera_swap", "Switch camera"))
        self._swap_button.clicked.connect(lambda: self.swapRequested.emit())
        self._snapshot_button = IconButton(
            "photo_camera", self._t("camera_snapshot", "Snapshot")
        )
        self._snapshot_button.clicked.connect(lambda: self.snapshotRequested.emit())
        for button in (self._torch_button, self._swap_button, self._snapshot_button):
            row_two.addWidget(button)
        row_two.addStretch(1)

        self._adjust_button = QPushButton(self._t("camera_adjust", "Adjust"))
        self._adjust_button.setObjectName("flatButton")
        self._adjust_button.clicked.connect(lambda: self.adjustRequested.emit())
        row_two.addWidget(self._adjust_button)
        self._quality_button = QPushButton(self._t("camera_quality", "Quality"))
        self._quality_button.setObjectName("flatButton")
        self._quality_button.clicked.connect(lambda: self.qualityRequested.emit())
        row_two.addWidget(self._quality_button)
        video_layout.addLayout(row_two)

        # Focus lives out here rather than in the Quality dialog: an AutoFocus
        # switch plus a manual distance slider that is dead while auto is on.
        row_three = QHBoxLayout()
        row_three.setSpacing(8)
        self._autofocus_button = QPushButton(self._t("camera_autofocus", "AutoFocus"))
        self._autofocus_button.setObjectName("flatButton")
        self._autofocus_button.setCheckable(True)
        self._autofocus_button.setChecked(True)
        self._autofocus_button.toggled.connect(self._on_autofocus_toggled)
        row_three.addWidget(self._autofocus_button)

        self._focus_slider = QSlider(Qt.Horizontal)
        self._focus_slider.setRange(0, 100)
        self._focus_slider.setValue(0)
        self._focus_slider.setEnabled(False)
        self._focus_slider.valueChanged.connect(self._on_focus_changed)
        row_three.addWidget(self._focus_slider, 1)

        self._focus_value = QLabel("0")
        self._focus_value.setObjectName("gainValue")
        self._focus_value.setFixedWidth(30)
        row_three.addWidget(self._focus_value)
        video_layout.addLayout(row_three)

        self._video_panel.setVisible(False)
        root.addWidget(self._video_panel)

        self._camera_controls = (
            self._rotate_left_button,
            self._rotate_right_button,
            self._flip_h_button,
            self._flip_v_button,
            self._zoom_in_button,
            self._zoom_out_button,
            self._torch_button,
            self._swap_button,
            self._snapshot_button,
            self._adjust_button,
            self._quality_button,
            self._autofocus_button,
            self._focus_slider,
        )

        # ---- tutorial (shown while no phone is connected) ---------------
        self._tutorial_card = QFrame()
        self._tutorial_card.setObjectName("tutorialCard")
        self._tutorial_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        tutorial = QVBoxLayout(self._tutorial_card)
        tutorial.setContentsMargins(20, 20, 20, 20)
        tutorial.setSpacing(10)

        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignCenter)
        tutorial.addWidget(self._qr_label)

        self._tutorial_title = QLabel(self._t("tutorial_title", "Waiting for Mobile"))
        self._tutorial_title.setAlignment(Qt.AlignCenter)
        tutorial.addWidget(self._tutorial_title)

        # one button per network address, so a PC with several interfaces
        # (Wi-Fi, Ethernet, Tailscale, ...) can be reached on any of them
        self._address_box = QVBoxLayout()
        self._address_box.setSpacing(4)
        self._address_buttons = []
        self._copy_buttons = []
        self._selected_address = None
        tutorial.addLayout(self._address_box)

        self._tutorial_pin = QLabel("")
        self._tutorial_pin.setAlignment(Qt.AlignCenter)
        self._tutorial_pin.setStyleSheet(
            "font-family: monospace; font-size: 18px; font-weight: bold;"
            " color: #4285F4;"
        )
        self._tutorial_pin.setVisible(False)
        tutorial.addWidget(self._tutorial_pin)

        self._tutorial_warn = QLabel(self._t("tutorial_warn", "The \u201cNot Secure\u201d warning is normal."))
        self._tutorial_warn.setObjectName("warnLabel")
        self._tutorial_warn.setAlignment(Qt.AlignCenter)
        self._tutorial_warn.setWordWrap(True)
        tutorial.addWidget(self._tutorial_warn)

        root.addWidget(self._tutorial_card)

        # ---- control area ----------------------------------------------
        self._control_area = QWidget()
        control = QVBoxLayout(self._control_area)
        control.setContentsMargins(0, 0, 0, 0)
        control.setSpacing(8)

        self._device_combo = _DeviceCombo()
        # Without this the combo demands room for the longest device name it
        # is given - "CABLE Input (VB-Audio Virtual Cable)" alone forced the
        # whole window wider than its default size.
        self._device_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self._device_combo.setMinimumContentsLength(16)
        self._device_combo.currentIndexChanged.connect(self._on_device_index_changed)
        control.addWidget(self._device_combo)

        gain_row = QHBoxLayout()
        self._gain_label = QLabel(self._t("desktop_gain", "Volume"))
        gain_row.addWidget(self._gain_label)
        gain_row.addStretch(1)
        self._gain_value_label = QLabel("1.0x")
        self._gain_value_label.setObjectName("gainValue")
        gain_row.addWidget(self._gain_value_label)
        control.addLayout(gain_row)

        self._gain_slider = QSlider(Qt.Horizontal)
        self._gain_slider.setRange(0, 30)
        self._gain_slider.setValue(10)
        self._gain_slider.valueChanged.connect(self._on_gain_slider)
        control.addWidget(self._gain_slider)

        pad_row = QHBoxLayout()
        pad_row.addStretch(1)
        self._mic_button = MicButton()
        self._mic_button.clicked.connect(lambda: self.muteToggled.emit())
        pad_row.addWidget(self._mic_button)
        # Camera sits beside the microphone: same phone, same size, one tap.
        self._camera_button = CameraToggle()
        self._camera_button.clicked.connect(lambda: self.cameraToggleRequested.emit())
        pad_row.addWidget(self._camera_button)
        pad_row.addStretch(1)
        control.addLayout(pad_row)

        root.addWidget(self._control_area)
        self._control_area.setVisible(False)

        self._connect_button = QPushButton("")
        self._connect_button.setObjectName("primaryButton")
        self._connect_button.clicked.connect(self._on_connect_clicked)
        root.addWidget(self._connect_button)

        # Everything above is packed from the top; this trailing stretch soaks
        # up any spare height so no single control gets inflated by it.
        root.addStretch(1)

        # Everything lives in a scroll area so the layout minimum stays small.
        # Otherwise showing the address list or the microphone pad raises the
        # window's minimum height and Qt forces the window taller than the
        # user sized it, every time the connection state changes.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: #121212; }")
        scroll.setWidget(content)

        # The settings panel and its scrim are children of the container but
        # stay out of the layout, so they sit above the scroll area as an
        # overlay that slides in from the right edge.
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(scroll)
        self._container = container

        self._scrim = _Scrim(container)
        self._scrim.clicked.connect(lambda: self._set_settings_open(False))
        self._scrim.hide()

        self._settings_panel = self._build_settings_panel(container)
        self._settings_panel.hide()

        self._settings_anim = QPropertyAnimation(self._settings_panel, b"geometry", self)
        self._settings_anim.setDuration(220)
        self._settings_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._settings_anim.finished.connect(self._on_settings_anim_finished)

        self.setCentralWidget(container)
        self._layout_settings()

        self.setMinimumSize(360, 420)
        self.set_language(self._language)

    # ------------------------------------------------------------------
    # settings sidebar
    # ------------------------------------------------------------------
    def _build_settings_panel(self, parent):
        panel = QFrame(parent)
        panel.setObjectName("settingsPanel")
        panel.setStyleSheet(
            "QFrame#settingsPanel { background: #1a1a1a;"
            " border-left: 1px solid #2a2a2a; }"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(14)

        head = QHBoxLayout()
        self._settings_title = QLabel(self._t("settings_title", "Settings"))
        self._settings_title.setObjectName("headerTitle")
        head.addWidget(self._settings_title)
        head.addStretch(1)
        close_button = QPushButton("\u2715")
        close_button.setObjectName("flatButton")
        close_button.setFixedWidth(40)
        close_button.clicked.connect(lambda: self._set_settings_open(False))
        head.addWidget(close_button)
        layout.addLayout(head)

        self._settings_lang_label = QLabel(self._t("settings_language", "Language"))
        self._settings_lang_label.setObjectName("statusTitle")
        layout.addWidget(self._settings_lang_label)

        self._language_combo = _LanguageCombo()
        for code, key, fallback in (
            ("en_us", "lang_en", "English"),
            ("zh_cn", "lang_zh", "\u4e2d\u6587"),
            ("vi_vn", "lang_vi", "Ti\u1ebfng Vi\u1ec7t"),
        ):
            self._language_combo.addItem(self._t(key, fallback), code)
        self._language_combo.currentIndexChanged.connect(
            self._on_language_index_changed
        )
        layout.addWidget(self._language_combo)

        self._require_pin_check = QCheckBox(
            self._t("settings_require_pin", "Require PIN")
        )
        self._require_pin_check.toggled.connect(self.requirePinChanged.emit)
        layout.addWidget(self._require_pin_check)

        # One grid keeps both rows' labels, fields and Apply buttons in the same
        # columns, so they line up no matter how wide the label or button text is.
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        grid.setColumnMinimumWidth(0, LABEL_WIDTH)

        self._pin_label = QLabel(self._t("settings_pin", "PIN"))
        grid.addWidget(self._pin_label, 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        self._pin_edit = QLineEdit()
        self._pin_edit.setMaxLength(10)
        self._pin_edit.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"[0-9]{0,10}"))
        )
        self._pin_edit.setFixedWidth(FIELD_WIDTH)
        self._pin_edit.setStyleSheet(FIELD_STYLE)
        self._pin_edit.returnPressed.connect(self._emit_pin_changed)
        grid.addWidget(self._pin_edit, 0, 1)
        self._pin_apply_button = QPushButton(self._t("settings_pin_apply", "Apply"))
        self._pin_apply_button.setObjectName("flatButton")
        self._pin_apply_button.clicked.connect(self._emit_pin_changed)
        grid.addWidget(self._pin_apply_button, 0, 2)
        self._new_pin_button = QPushButton(self._t("settings_new_pin", "New PIN"))
        self._new_pin_button.setObjectName("flatButton")
        self._new_pin_button.clicked.connect(
            lambda: self.regeneratePinRequested.emit()
        )
        grid.addWidget(self._new_pin_button, 0, 3)

        self._port_label = QLabel(self._t("host_port", "Port"))
        grid.addWidget(self._port_label, 1, 0, Qt.AlignLeft | Qt.AlignVCenter)
        self._port_input = QLineEdit()
        self._port_input.setValidator(QIntValidator(1024, 65535, self))
        self._port_input.setFixedWidth(FIELD_WIDTH)
        self._port_input.setStyleSheet(FIELD_STYLE)
        self._port_input.returnPressed.connect(self._on_apply_port)
        grid.addWidget(self._port_input, 1, 1)
        self._apply_port_button = QPushButton(self._t("host_apply", "Apply"))
        self._apply_port_button.setObjectName("flatButton")
        self._apply_port_button.clicked.connect(self._on_apply_port)
        grid.addWidget(self._apply_port_button, 1, 2)

        grid.setColumnStretch(4, 1)
        layout.addLayout(grid)

        self._startup_check = QCheckBox(
            self._t("settings_start_with_windows", "Start with Windows")
        )
        self._startup_check.toggled.connect(self.startupChanged.emit)
        self._startup_check.setVisible(sys.platform == "win32")
        layout.addWidget(self._startup_check)

        self._close_tray_check = QCheckBox(
            self._t("settings_close_to_tray", "Minimize to tray on close")
        )
        # Match the behaviour the window already has, until the controller
        # loads the saved choice.
        self._close_tray_check.setChecked(self.close_to_tray)
        self._close_tray_check.toggled.connect(self._on_close_to_tray_toggled)
        layout.addWidget(self._close_tray_check)

        self._about_button = QPushButton(self._t("header_about", "About"))
        self._about_button.setObjectName("flatButton")
        self._about_button.clicked.connect(lambda: self.aboutRequested.emit())
        layout.addWidget(self._about_button)

        layout.addStretch(1)

        self._settings_version = QLabel(self._version)
        self._settings_version.setObjectName("versionLabel")
        layout.addWidget(self._settings_version)

        return panel

    def _on_language_index_changed(self, index):
        code = self._language_combo.itemData(index)
        if code and code != self._language:
            self.languageChanged.emit(code)

    def set_pin(self, pin, required):
        self._pin = pin or ""
        self._pin_required = bool(required)
        self._require_pin_check.blockSignals(True)
        self._require_pin_check.setChecked(self._pin_required)
        self._require_pin_check.blockSignals(False)
        self._pin_edit.blockSignals(True)
        self._pin_edit.setText(self._pin)
        self._pin_edit.blockSignals(False)
        self._refresh_pin_labels()

    def _emit_pin_changed(self):
        self.pinChanged.emit(self._pin_edit.text().strip())

    def set_startup_enabled(self, enabled):
        self._startup_check.blockSignals(True)
        self._startup_check.setChecked(bool(enabled))
        self._startup_check.blockSignals(False)

    def set_close_to_tray(self, enabled):
        self.close_to_tray = bool(enabled)
        self._close_tray_check.blockSignals(True)
        self._close_tray_check.setChecked(self.close_to_tray)
        self._close_tray_check.blockSignals(False)

    def _on_close_to_tray_toggled(self, enabled):
        self.close_to_tray = bool(enabled)
        self.closeToTrayChanged.emit(self.close_to_tray)

    def _refresh_pin_labels(self):
        if self._pin_required and self._pin:
            self._tutorial_pin.setText(f'{self._t("settings_pin", "PIN")}: {self._pin}')
            self._tutorial_pin.setVisible(True)
        else:
            self._tutorial_pin.setText("")
            self._tutorial_pin.setVisible(False)

    def _layout_settings(self):
        width = self._container.width()
        height = self._container.height()
        panel_width = min(SETTINGS_PANEL_WIDTH, max(0, width))
        x = width - panel_width if self._settings_open else width
        self._settings_panel.setGeometry(x, 0, panel_width, height)
        self._scrim.setGeometry(0, 0, width, height)

    def _set_settings_open(self, open_):
        if open_ == self._settings_open:
            return
        self._settings_open = open_

        width = self._container.width()
        height = self._container.height()
        panel_width = min(SETTINGS_PANEL_WIDTH, max(0, width))
        end_x = width - panel_width if open_ else width

        if open_:
            self._scrim.setGeometry(0, 0, width, height)
            self._scrim.show()
            self._scrim.raise_()
            self._settings_panel.show()
            self._settings_panel.raise_()
        else:
            self._scrim.raise_()

        self._settings_anim.stop()
        self._settings_anim.setStartValue(
            QRect(self._settings_panel.x(), 0, panel_width, height)
        )
        self._settings_anim.setEndValue(QRect(end_x, 0, panel_width, height))
        self._settings_anim.start()

    def _on_settings_anim_finished(self):
        if not self._settings_open:
            self._settings_panel.hide()
            self._scrim.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_container", None) is not None:
            self._layout_settings()

    # ------------------------------------------------------------------
    # slots
    # ------------------------------------------------------------------
    def _on_connect_clicked(self):
        if self._active:
            self.disconnectRequested.emit()
        else:
            self.connectRequested.emit()

    def _on_gain_slider(self, raw):
        gain = raw / 10.0
        self._gain_value_label.setText(f"{gain:.1f}x")
        self.gainChanged.emit(gain)

    def _on_device_index_changed(self, index):
        if index < 0:
            return
        # The closed box elides a long name; keep the whole one reachable.
        self._device_combo.setToolTip(self._device_combo.itemText(index))
        device = self._device_combo.itemData(index)
        if device is not None:
            self.deviceChanged.emit(int(device))

    # ------------------------------------------------------------------
    # language
    # ------------------------------------------------------------------
    def set_language(self, language):
        self._language = language
        position = self._language_combo.findData(language)
        if position >= 0 and position != self._language_combo.currentIndex():
            self._language_combo.blockSignals(True)
            self._language_combo.setCurrentIndex(position)
            self._language_combo.blockSignals(False)
        self.retranslate()

    def retranslate(self):
        self._settings_title.setText(self._t("settings_title", "Settings"))
        self._settings_lang_label.setText(self._t("settings_language", "Language"))
        self._require_pin_check.setText(self._t("settings_require_pin", "Require PIN"))
        self._pin_label.setText(self._t("settings_pin", "PIN"))
        self._pin_apply_button.setText(self._t("settings_pin_apply", "Apply"))
        self._new_pin_button.setText(self._t("settings_new_pin", "New PIN"))
        self._startup_check.setText(
            self._t("settings_start_with_windows", "Start with Windows")
        )
        self._close_tray_check.setText(
            self._t("settings_close_to_tray", "Minimize to tray on close")
        )
        self._refresh_pin_labels()
        self._settings_button.setToolTip(self._t("settings_title", "Settings"))
        self._about_button.setText(self._t("header_about", "About"))
        self._retranslate_camera()
        self._status_title.setText(self._t("status_label", "Mobile Connection"))
        self._gain_label.setText(self._t("desktop_gain", "Volume"))
        self._port_label.setText(self._t("host_port", "Port"))
        self._apply_port_button.setText(self._t("host_apply", "Apply"))
        self._tutorial_title.setText(self._t("tutorial_title", "Waiting for Mobile"))
        self._tutorial_warn.setText(
            self._t("tutorial_warn", "The \u201cNot Secure\u201d warning is normal.")
        )
        for button in self._copy_buttons:
            button.setText(self._t("host_copy", "Copy"))
        self.set_active(self._active)
        self._refresh_status()

    # ------------------------------------------------------------------
    # updates coming from the session
    # ------------------------------------------------------------------
    def set_level_provider(self, provider):
        self._level_provider = provider
        self._mic_button.set_level_provider(provider)

    def set_devices(self, devices, current_index=None):
        self._device_combo.blockSignals(True)
        self._device_combo.clear()
        for index, name in devices:
            self._device_combo.addItem(name, index)
        if current_index is not None:
            position = self._device_combo.findData(current_index)
            if position >= 0:
                self._device_combo.setCurrentIndex(position)
        self._device_combo.blockSignals(False)
        self._device_combo.setToolTip(self._device_combo.currentText())

    def set_gain(self, gain):
        self._gain_slider.blockSignals(True)
        self._gain_slider.setValue(int(round(gain * 10)))
        self._gain_value_label.setText(f"{gain:.1f}x")
        self._gain_slider.blockSignals(False)

    def set_addresses(self, addresses):
        while self._address_box.count():
            item = self._address_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            nested = item.layout()
            if nested is not None:
                while nested.count():
                    sub_item = nested.takeAt(0)
                    sub_widget = sub_item.widget()
                    if sub_widget is not None:
                        sub_widget.deleteLater()

        self._address_buttons = []
        self._copy_buttons = []

        for url in addresses:
            row = QHBoxLayout()
            row.setSpacing(6)

            button = QPushButton(url)
            button.setObjectName("addressButton")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, target=url: self.addressSelected.emit(target))
            row.addWidget(button, 1)

            copy_button = QPushButton(self._t("host_copy", "Copy"))
            copy_button.setObjectName("copyButton")
            copy_button.setCursor(Qt.PointingHandCursor)
            copy_button.clicked.connect(
                lambda _=False, target=url, btn=copy_button: self._copy_address(target, btn)
            )
            row.addWidget(copy_button, 0)

            self._address_box.addLayout(row)
            self._address_buttons.append(button)
            self._copy_buttons.append(copy_button)

        if addresses:
            self.addressSelected.emit(addresses[0])

    def _copy_address(self, url, button):
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(url)
        button.setText(self._t("host_copied", "Copied"))
        QTimer.singleShot(1200, lambda: self._reset_copy_button(button))

    def _reset_copy_button(self, button):
        # The row may have been rebuilt while the timer was pending.
        try:
            button.setText(self._t("host_copy", "Copy"))
        except RuntimeError:
            pass

    def set_selected_address(self, url):
        self._selected_address = url
        for button in self._address_buttons:
            name = "addressButtonSelected" if button.text() == url else "addressButton"
            if button.objectName() != name:
                button.setObjectName(name)
                button.style().unpolish(button)
                button.style().polish(button)

    def set_port(self, port):
        self._port_input.blockSignals(True)
        self._port_input.setText(str(int(port)))
        self._port_input.blockSignals(False)

    def _on_apply_port(self):
        text = self._port_input.text().strip()
        if not text.isdigit():
            return
        port = int(text)
        if 1024 <= port <= 65535:
            self.portChangeRequested.emit(port)

    def set_qr(self, png_bytes):
        pixmap = QPixmap()
        if pixmap.loadFromData(png_bytes, "PNG"):
            self._qr_label.setPixmap(pixmap)
            self._qr_label.setVisible(True)

    def set_active(self, active):
        self._active = active
        self._connect_button.setText(
            self._t("desktop_disconnect", "Disconnect")
            if active
            else self._t("desktop_connect", "Connect")
        )
        self._connect_button.setObjectName("dangerButton" if active else "primaryButton")
        self._connect_button.style().unpolish(self._connect_button)
        self._connect_button.style().polish(self._connect_button)

    # ------------------------------------------------------------------
    # camera
    # ------------------------------------------------------------------
    def set_frame_source(self, source):
        self._preview_area.set_frame_source(source)

    def set_camera_placeholder(self, text):
        self._preview_area.set_placeholder(text)

    def set_camera_available(self, available, name=""):
        self._camera_available = bool(available)
        for button in self._camera_controls:
            button.setEnabled(self._camera_available)
        self._preview_area.set_placeholder(
            self._t("camera_waiting", "Waiting for the phone camera...")
            if self._camera_available
            else self._t("camera_none", "No camera on this phone")
        )

    def set_camera_streaming(self, streaming):
        self._camera_streaming = bool(streaming)
        if not streaming:
            self._preview_area.set_stats(None)
        self._preview_area.set_streaming(self._camera_streaming)
        self._camera_button.set_state(self._camera_streaming, self._presence)

    def set_camera_stats(self, sample):
        self._preview_area.set_stats(sample)

    def _nudge_zoom(self, delta):
        self._zoom = max(1.0, min(10.0, self._zoom + delta))
        self._zoom_label.setText(f"{self._zoom:.1f}x")
        self.zoomChanged.emit(self._zoom)

    def _on_autofocus_toggled(self, checked):
        # Manual distance only makes sense once auto focus is off.
        self._focus_slider.setEnabled(not checked)
        self.autoFocusToggled.emit(bool(checked))

    def _on_focus_changed(self, value):
        self._focus_value.setText(str(int(value)))
        self.focusChanged.emit(int(value))

    def _retranslate_camera(self):
        self._adjust_button.setText(self._t("camera_adjust", "Adjust"))
        self._quality_button.setText(self._t("camera_quality", "Quality"))
        self._autofocus_button.setText(self._t("camera_autofocus", "AutoFocus"))
        self._rotate_left_button.setToolTip(self._t("camera_rotate_left", "Rotate left"))
        self._rotate_right_button.setToolTip(self._t("camera_rotate_right", "Rotate right"))
        self._flip_h_button.setToolTip(self._t("camera_flip_h", "Flip horizontally"))
        self._flip_v_button.setToolTip(self._t("camera_flip_v", "Flip vertically"))
        self._zoom_in_button.setToolTip(self._t("camera_zoom_in", "Zoom in"))
        self._zoom_out_button.setToolTip(self._t("camera_zoom_out", "Zoom out"))
        self._torch_button.setToolTip(self._t("camera_torch", "Torch"))
        self._swap_button.setToolTip(self._t("camera_swap", "Switch camera"))
        self._snapshot_button.setToolTip(self._t("camera_snapshot", "Snapshot"))
        self._camera_button.setToolTip(self._t("camera_toggle", "Camera"))
        self.set_camera_available(self._camera_available)

    def set_link_state(self, state):
        self._link_up = state == "connected"
        self._refresh_status()

    def set_presence(self, connected):
        self._presence = connected
        self._tutorial_card.setVisible(not connected)
        self._control_area.setVisible(connected)
        self._video_panel.setVisible(connected)
        self._camera_button.set_state(self._camera_streaming, connected)
        self._update_mic_state()
        self._refresh_status()

    def set_rtc_state(self, state):
        self._rtc_state = state or "new"
        self._refresh_status()

    def set_muted(self, muted):
        self._muted = muted
        self._update_mic_state()
        self._refresh_status()

    def _update_mic_state(self):
        if not self._presence:
            self._mic_button.set_state("idle")
        elif self._muted:
            self._mic_button.set_state("muted")
        else:
            self._mic_button.set_state("active")

    def _refresh_status(self):
        if not self._link_up:
            color, text = DOT_IDLE, self._t("status_offline", "Not connected to service")
        elif not self._presence:
            color, text = DOT_IDLE, self._t("status_wait", "Waiting for device...")
        elif self._rtc_state in ("connected", "completed"):
            if self._muted:
                color, text = DOT_WARN, self._t("state_muted", "Desktop Muted")
            else:
                color, text = DOT_OK, self._t("status_connected", "Mobile Connected")
        elif self._rtc_state in ("failed", "closed"):
            color, text = DOT_ERROR, self._t("status_error", "Connection Failed")
        else:
            color, text = DOT_WARN, self._t("status_connecting", "Connecting...")

        self._dot.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
        self._status_text.setText(text)
        self._status_text.setStyleSheet(f"color: {color};")

    def closeEvent(self, event):
        if getattr(self, "allow_close", False):
            event.accept()
            return
        if not self.close_to_tray:
            # "Minimize to tray on close" is off, so closing means quitting.
            event.accept()
            self.quitRequested.emit()
            return
        event.ignore()
        self.hide()
        on_hidden = getattr(self, "on_hidden", None)
        if on_hidden is not None:
            on_hidden()
