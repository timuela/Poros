"""Dialogs for stream quality and image adjustment.

These used to be a whole second window; the video itself now lives in the main
window, so only the settings still need a dialog of their own.
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

FPS_CHOICES = (15, 24, 30, 60)

# Mirror of the phone's filter catalog: sliders for corrections, a dropdown for
# the single active effect.
CORRECTION_FILTERS = (
    "Brightness",
    "Contrast",
    "Exposure",
    "Gamma",
    "Saturation",
    "Temperature",
    "Sharpness",
)

EFFECT_FILTERS = (
    "None",
    "Grey Scale",
    "Sepia",
    "Negative",
    "Early Bird",
    "70s Style",
    "Lamoish",
    "Cartoon",
    "Duotone",
    "Halftone Lines",
    "Pixelated",
    "Polygonization",
    "Rainbow",
    "Money",
    "Zebra",
    "Edge Detection",
    "Blur",
    "Glitch",
    "Noise",
    "Analog TV",
    "Swirl",
    "Ripple",
    "Fire",
    "Snow",
)


class QualityDialog(QDialog):
    """Resolution, frame rate, bitrate mode, codec and focus."""

    applied = Signal(dict)

    def __init__(self, t, parent=None):
        super().__init__(parent)
        self._t = t
        self.setWindowTitle(t("quality_title", "Stream quality"))
        self.setModal(True)
        self.setMinimumWidth(360)
        self._resolutions = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)

        video = QGroupBox(self._t("quality_video", "Video quality"))
        form = QFormLayout(video)

        self._resolution_combo = QComboBox()
        form.addRow(self._t("quality_resolution", "Resolution"), self._resolution_combo)

        self._fps_combo = QComboBox()
        for fps in FPS_CHOICES:
            self._fps_combo.addItem(f"{fps} fps", fps)
        self._fps_combo.setCurrentIndex(FPS_CHOICES.index(30))
        form.addRow(self._t("quality_fps", "Frame rate"), self._fps_combo)

        self._codec_combo = QComboBox()
        self._codec_combo.addItem("H.264", "h264")
        self._codec_combo.addItem("H.265", "h265")
        form.addRow(self._t("quality_codec", "Codec"), self._codec_combo)

        self._transport_combo = QComboBox()
        self._transport_combo.addItem("TCP", "tcp")
        self._transport_combo.addItem("UDP", "udp")
        self._transport_combo.setToolTip(
            self._t(
                "camera_transport_hint",
                "TCP is reliable; UDP is lighter but can drop frames",
            )
        )
        form.addRow(self._t("quality_transport", "Transport"), self._transport_combo)

        mode_row = QWidget()
        mode = QHBoxLayout(mode_row)
        mode.setContentsMargins(0, 0, 0, 0)
        self._static_radio = QRadioButton(self._t("quality_static", "Static"))
        self._adaptive_radio = QRadioButton(self._t("quality_adaptive", "Adaptive"))
        self._static_radio.setChecked(True)
        self._static_radio.toggled.connect(self._refresh_bitrate_enabled)
        mode.addWidget(self._static_radio)
        mode.addWidget(self._adaptive_radio)
        mode.addStretch(1)
        form.addRow(self._t("quality_bitrate_mode", "Bitrate"), mode_row)

        self._bitrate_edit = QLineEdit("6000")
        self._bitrate_edit.setFixedWidth(90)
        form.addRow(self._t("quality_bitrate", "kbps"), self._bitrate_edit)

        self._min_edit = QLineEdit("2000")
        self._min_edit.setFixedWidth(90)
        self._min_row_label = QLabel(self._t("quality_min", "Min kbps"))
        form.addRow(self._min_row_label, self._min_edit)

        self._max_edit = QLineEdit("12000")
        self._max_edit.setFixedWidth(90)
        self._max_row_label = QLabel(self._t("quality_max", "Max kbps"))
        form.addRow(self._max_row_label, self._max_edit)

        root.addWidget(video)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self
        )
        buttons.button(QDialogButtonBox.Ok).setText(self._t("host_apply", "Apply"))
        buttons.button(QDialogButtonBox.Cancel).setText(self._t("cancel", "Cancel"))
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._refresh_bitrate_enabled()

    def _refresh_bitrate_enabled(self):
        static = self._static_radio.isChecked()
        self._bitrate_edit.setEnabled(static)
        self._min_edit.setEnabled(not static)
        self._max_edit.setEnabled(not static)
        self._min_row_label.setEnabled(not static)
        self._max_row_label.setEnabled(not static)

    def set_resolutions(self, resolutions):
        self._resolutions = [tuple(r) for r in (resolutions or [])]
        current = self._resolution_combo.currentData()
        self._resolution_combo.clear()
        for width, height in self._resolutions:
            # Store a plain string: QComboBox.findData compares the wrapped
            # Python object, and a tuple does not compare equal reliably, which
            # is why the dialog kept snapping back to the largest resolution.
            self._resolution_combo.addItem(f"{width} \u00d7 {height}", f"{width}x{height}")
        if current is not None:
            position = self._resolution_combo.findData(current)
            if position >= 0:
                self._resolution_combo.setCurrentIndex(position)
        if self._resolution_combo.count() == 0:
            self._resolution_combo.addItem("1920 \u00d7 1080", "1920x1080")

    @staticmethod
    def _resolution_value(text):
        try:
            width, height = str(text).split("x")
            return int(width), int(height)
        except Exception:
            return 1920, 1080

    def set_state(self, state):
        state = state or {}
        resolution = f"{state.get('width')}x{state.get('height')}"
        position = self._resolution_combo.findData(resolution)
        if position >= 0:
            self._resolution_combo.setCurrentIndex(position)
        position = self._fps_combo.findData(state.get("fps"))
        if position >= 0:
            self._fps_combo.setCurrentIndex(position)
        position = self._codec_combo.findData(state.get("codec"))
        if position >= 0:
            self._codec_combo.setCurrentIndex(position)
        position = self._transport_combo.findData(state.get("transport"))
        if position >= 0:
            self._transport_combo.setCurrentIndex(position)

        adaptive = state.get("adaptive")
        self._adaptive_radio.setChecked(bool(adaptive))
        self._static_radio.setChecked(not adaptive)
        if adaptive:
            self._min_edit.setText(str(state.get("min_bitrate", 2000)))
            self._max_edit.setText(str(state.get("max_bitrate", 12000)))
        else:
            self._bitrate_edit.setText(str(state.get("bitrate", 6000)))
        self._refresh_bitrate_enabled()

    @staticmethod
    def _int(text, fallback):
        try:
            return int(str(text).strip())
        except (TypeError, ValueError):
            return fallback

    def _on_accept(self):
        width, height = self._resolution_value(self._resolution_combo.currentData())
        settings = {
            "width": width,
            "height": height,
            "fps": int(self._fps_combo.currentData() or 30),
            "codec": self._codec_combo.currentData() or "h264",
            "transport": self._transport_combo.currentData() or "tcp",
            "adaptive": self._adaptive_radio.isChecked(),
            "bitrate": self._int(self._bitrate_edit.text(), 6000),
            "min_bitrate": self._int(self._min_edit.text(), 2000),
            "max_bitrate": self._int(self._max_edit.text(), 12000),
        }
        self.applied.emit(settings)
        self.accept()


class AdjustDialog(QDialog):
    """Correction sliders and the single active effect, mirroring the phone."""

    correctionChanged = Signal(str, int)
    effectChanged = Signal(str)
    resetRequested = Signal()

    def __init__(self, t, parent=None):
        super().__init__(parent)
        self._t = t
        self.setWindowTitle(t("adjust_title", "Image adjustment"))
        self.setModal(True)
        self.setMinimumWidth(340)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)

        # A drag fires valueChanged dozens of times a second, and every event is
        # a round trip that re-configures the phone's GL filter chain, so send
        # at a sane rate while dragging and once more when the handle is let go.
        self._pending_filter = None
        self._emit_timer = QTimer(self)
        self._emit_timer.setSingleShot(True)
        self._emit_timer.setInterval(120)
        self._emit_timer.timeout.connect(self._flush_pending)

        self._effect_combo = QComboBox()
        self._effect_combo.addItems(EFFECT_FILTERS)
        self._effect_combo.currentTextChanged.connect(
            lambda name: self.effectChanged.emit(name)
        )
        effect_row = QFormLayout()
        effect_row.addRow(self._t("adjust_effect", "Effect"), self._effect_combo)
        root.addLayout(effect_row)

        self._sliders = {}
        for name in CORRECTION_FILTERS:
            box = QGroupBox(name)
            layout = QHBoxLayout(box)
            layout.setContentsMargins(8, 6, 8, 6)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(50)
            value = QLabel("50")
            value.setFixedWidth(30)
            slider.valueChanged.connect(
                lambda raw, l=value, n=name: self._on_slider(n, raw, l)
            )
            slider.sliderReleased.connect(self._flush_pending)
            layout.addWidget(slider, 1)
            layout.addWidget(value)
            self._sliders[name] = slider
            root.addWidget(box)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, Qt.Horizontal, self)
        buttons.button(QDialogButtonBox.Close).setText(self._t("dialog_close", "Close"))
        reset = QPushButton(self._t("adjust_reset", "Reset all"))
        buttons.addButton(reset, QDialogButtonBox.ResetRole)
        reset.clicked.connect(self._on_reset)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_slider(self, name, raw, label):
        label.setText(str(raw))
        self._pending_filter = (name, int(raw))
        if not self._emit_timer.isActive():
            self._emit_timer.start()

    def _flush_pending(self):
        self._emit_timer.stop()
        pending, self._pending_filter = self._pending_filter, None
        if pending is not None:
            self.correctionChanged.emit(pending[0], pending[1])

    def _on_reset(self):
        self._pending_filter = None
        self._emit_timer.stop()
        for slider in self._sliders.values():
            slider.blockSignals(True)
            slider.setValue(50)
            slider.blockSignals(False)
        self._effect_combo.blockSignals(True)
        self._effect_combo.setCurrentText("None")
        self._effect_combo.blockSignals(False)
        self.resetRequested.emit()
