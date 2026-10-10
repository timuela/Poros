import logging

import socketio

log = logging.getLogger(__name__)


class SignalingClient:
    """Socket.IO client connecting the desktop app to the Poros server."""

    def __init__(self, session):
        self._session = session
        self._sio = socketio.AsyncClient(ssl_verify=False, reconnection=True)

        self._sio.on("connect", self._on_connect)
        self._sio.on("disconnect", self._on_disconnect)
        self._sio.on("connect_error", self._on_connect_error)
        self._sio.on("presence", self._on_presence)
        self._sio.on("offer", self._on_offer)
        self._sio.on("ice_candidate", self._on_ice_candidate)
        self._sio.on("toggle_mute", self._on_toggle_mute)
        self._sio.on("camera_descriptor", self._on_camera_descriptor)
        self._sio.on("camera_status", self._on_camera_status)

    @property
    def connected(self):
        return self._sio.connected

    async def connect(self, url):
        await self._sio.connect(url)

    async def disconnect(self):
        if self._sio.connected:
            await self._sio.disconnect()

    async def emit_answer(self, sdp):
        await self._sio.emit("answer", {"type": "answer", "sdp": sdp})

    async def emit_candidate(self, candidate, sdp_mid, sdp_m_line_index):
        await self._sio.emit(
            "ice_candidate",
            {
                "candidate": candidate,
                "sdpMid": sdp_mid,
                "sdpMLineIndex": sdp_m_line_index,
            },
        )

    async def emit_toggle_mute(self):
        await self._sio.emit("toggle_mute")

    async def emit_camera_start(self, width, height, fps):
        await self._sio.emit(
            "camera_start", {"width": int(width), "height": int(height), "fps": int(fps)}
        )

    async def emit_camera_stop(self):
        await self._sio.emit("camera_stop", {})

    async def emit_camera_command(self, op, value=None):
        await self._sio.emit("camera_command", {"op": str(op), "value": value})

    async def _on_connect(self):
        await self._sio.emit("join", {"role": "desktop"})
        await self._session.on_signaling_connected()

    async def _on_disconnect(self):
        await self._session.on_signaling_disconnected()

    async def _on_connect_error(self, data):
        await self._session.on_signaling_error(str(data))

    async def _on_presence(self, data):
        mobile = bool(data.get("mobile")) if isinstance(data, dict) else False
        await self._session.on_presence(mobile)

    async def _on_offer(self, data):
        await self._session.on_offer(data)

    async def _on_ice_candidate(self, data):
        await self._session.on_ice_candidate(data)

    async def _on_toggle_mute(self):
        await self._session.on_toggle_mute()

    async def _on_camera_descriptor(self, data):
        await self._session.on_camera_descriptor(data)

    async def _on_camera_status(self, data):
        await self._session.on_camera_status(data)
