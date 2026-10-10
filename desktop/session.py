import logging

from platforms.base import translate

from desktop.audio import AudioOutput
from desktop.webrtc import WebRtcReceiver

log = logging.getLogger(__name__)


class DesktopSession:
    """Owns the signalling client, the WebRTC receiver and the audio output.

    Every method that touches WebRTC or the network must run on the asyncio
    thread. Commands arriving from Qt are scheduled onto it by the app.
    """

    def __init__(self, feedback, platform, t=None):
        self._feedback = feedback
        self._platform = platform
        # Reports errors in the language the desktop app is using.
        self._t = t
        self._audio = AudioOutput()
        self._webrtc = WebRtcReceiver(
            on_pcm=self._audio.push,
            on_ice=self._on_local_candidate,
            on_state=self._on_rtc_state,
        )
        # Created in start(), on the asyncio thread, so importing the socket.io
        # client is not part of the window's startup path.
        self._signaling = None
        self._schedule = None
        self._muted = False
        self._active = False
        self._camera_descriptor = None

    def set_scheduler(self, schedule):
        """Provide a callable(coro) that schedules work on the asyncio loop."""
        self._schedule = schedule

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    async def start(self, url, device_index):
        from desktop.signaling import SignalingClient

        self._active = True
        self._feedback.set_rtc_state("new")
        self._open_device(device_index)
        if self._signaling is None:
            self._signaling = SignalingClient(self)
        try:
            await self._signaling.connect(url)
        except Exception as exc:
            self._active = False
            self._feedback.report_error(
                translate(
                    self._t,
                    "error_connect",
                    "Could not connect to the server: {detail}",
                    detail=exc,
                )
            )

    async def stop(self):
        self._active = False
        await self._webrtc.close()
        if self._signaling is not None:
            await self._signaling.disconnect()
        self._audio.stop()
        # Late callbacks from the closing peer connection are ignored now that
        # the session is inactive, so clear the state the UI is showing.
        self._feedback.set_rtc_state("new")
        self._feedback.set_presence(False)

    def _open_device(self, device_index):
        if device_index is None:
            return
        try:
            self._audio.start(device_index)
        except Exception as exc:
            self._feedback.report_error(
                translate(
                    self._t,
                    "error_audio_device",
                    "Could not open the audio output device: {detail}",
                    detail=exc,
                )
            )

    # ------------------------------------------------------------------
    # commands from the UI / tray
    # ------------------------------------------------------------------
    def select_device(self, device_index):
        if self._active:
            self._open_device(device_index)

    def set_gain(self, gain):
        self._audio.set_gain(gain)

    def level(self):
        return self._audio.level

    def toggle_mute(self, broadcast=True):
        self._muted = not self._muted
        self._audio.set_muted(self._muted)
        self._feedback.set_muted(self._muted)

        # Tell the phone to follow, but never echo back to ourselves.
        if (
            broadcast
            and self._signaling is not None
            and self._signaling.connected
            and self._schedule is not None
        ):
            self._schedule(self._signaling.emit_toggle_mute())

    # ------------------------------------------------------------------
    # signalling callbacks
    # ------------------------------------------------------------------
    async def on_signaling_connected(self):
        self._feedback.set_link_state("connected")

    async def on_signaling_disconnected(self):
        if not self._active:
            return
        self._feedback.set_link_state("disconnected")

    async def on_signaling_error(self, message):
        if not self._active:
            return
        self._feedback.set_link_state("disconnected")
        self._feedback.report_error(
            translate(
                self._t,
                "error_signalling",
                "Signalling connection failed: {detail}",
                detail=message,
            )
        )

    async def on_presence(self, mobile_connected):
        if not self._active:
            return
        self._feedback.set_presence(mobile_connected)
        if not mobile_connected:
            await self._webrtc.close()
            self._feedback.set_rtc_state("new")
            # The phone that was offering its camera is gone; drop its descriptor
            # so the UI does not keep a dead device on screen.
            self._camera_descriptor = None
            self._feedback.set_camera_descriptor(None)

    async def on_offer(self, data):
        if not self._active:
            return
        sdp = data.get("sdp") if isinstance(data, dict) else None
        if not sdp:
            return
        try:
            answer = await self._webrtc.handle_offer(sdp)
        except Exception as exc:
            self._feedback.report_error(
                translate(
                    self._t,
                    "error_webrtc",
                    "WebRTC negotiation failed: {detail}",
                    detail=exc,
                )
            )
            return
        await self._signaling.emit_answer(answer)

    async def on_ice_candidate(self, data):
        if not self._active or not isinstance(data, dict):
            return
        await self._webrtc.add_candidate(
            data.get("candidate"), data.get("sdpMid"), data.get("sdpMLineIndex")
        )

    async def on_toggle_mute(self):
        if not self._active:
            return
        self.toggle_mute(broadcast=False)

    # ------------------------------------------------------------------
    # camera control (video rides a separate RTSP stream)
    # ------------------------------------------------------------------
    async def on_camera_descriptor(self, data):
        if not self._active or not isinstance(data, dict):
            return
        self._camera_descriptor = data
        self._feedback.set_camera_descriptor(data)

    async def on_camera_status(self, data):
        if not self._active or not isinstance(data, dict):
            return
        self._feedback.set_camera_status(
            str(data.get("state", "")), str(data.get("detail", ""))
        )

    @property
    def camera_descriptor(self):
        return self._camera_descriptor

    def start_camera(self, width, height, fps):
        if self._schedule is None or self._signaling is None:
            return
        self._schedule(self._signaling.emit_camera_start(width, height, fps))

    def stop_camera(self):
        if self._schedule is None or self._signaling is None:
            return
        self._schedule(self._signaling.emit_camera_stop())

    def send_camera_command(self, op, value=None):
        if self._schedule is None or self._signaling is None:
            return
        self._schedule(self._signaling.emit_camera_command(op, value))

    # ------------------------------------------------------------------
    # WebRTC callbacks
    # ------------------------------------------------------------------
    async def _on_local_candidate(self, candidate, sdp_mid, sdp_m_line_index):
        if not self._active:
            return
        if (
            self._signaling is None
            or candidate is None
            or not self._signaling.connected
        ):
            return
        await self._signaling.emit_candidate(candidate, sdp_mid, sdp_m_line_index)

    async def _on_rtc_state(self, state):
        if not self._active:
            return
        self._feedback.set_rtc_state(state)
