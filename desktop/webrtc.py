import asyncio
import logging

# aiortc (and the aioice/numpy/av it drags in) is ~0.7s of imports that are not
# needed until a phone actually sends an offer, so it is imported at first use
# to keep it off the startup path.

log = logging.getLogger(__name__)


def frame_to_pcm(frame):
    """Convert a decoded audio frame to an int16 array shaped (samples, channels)."""
    import numpy as np

    data = frame.to_ndarray()
    channels = frame.layout.nb_channels

    if frame.format.is_planar:
        data = data.T
    else:
        data = data.reshape(-1, channels)

    data = np.ascontiguousarray(data)

    if data.dtype != np.int16:
        if np.issubdtype(data.dtype, np.floating):
            data = np.clip(data, -1.0, 1.0) * 32767.0
        data = data.astype(np.int16)

    return data


def candidate_to_sdp(candidate):
    """Rebuild the SDP candidate line from an aiortc RTCIceCandidate."""
    from aioice import Candidate

    parsed = Candidate(
        foundation=candidate.foundation,
        component=candidate.component,
        transport=candidate.protocol,
        priority=candidate.priority,
        host=candidate.ip,
        port=candidate.port,
        type=candidate.type,
        related_address=candidate.relatedAddress,
        related_port=candidate.relatedPort,
        tcptype=candidate.tcpType,
    )
    return "candidate:" + parsed.to_sdp()


def candidate_from_string(candidate, sdp_mid, sdp_m_line_index):
    """Parse a trickled SDP candidate string into an aiortc RTCIceCandidate."""
    from aioice import Candidate
    from aiortc import RTCIceCandidate

    raw = candidate.strip()
    if raw.startswith("a="):
        raw = raw[2:]
    if raw.startswith("candidate:"):
        raw = raw[len("candidate:") :]

    parsed = Candidate.from_sdp(raw)
    return RTCIceCandidate(
        component=parsed.component,
        foundation=parsed.foundation,
        ip=parsed.host,
        port=parsed.port,
        priority=parsed.priority,
        protocol=parsed.transport,
        type=parsed.type,
        relatedAddress=parsed.related_address,
        relatedPort=parsed.related_port,
        sdpMid=sdp_mid,
        sdpMLineIndex=sdp_m_line_index,
        tcpType=parsed.tcptype,
    )


class WebRtcReceiver:
    """WebRTC answerer that decodes the incoming audio track."""

    def __init__(self, on_pcm, on_ice, on_state=None):
        self._on_pcm = on_pcm
        self._on_ice = on_ice
        self._on_state = on_state
        self._pc = None
        self._pump_task = None

    async def handle_offer(self, offer_sdp):
        from aiortc import (
            RTCConfiguration,
            RTCPeerConnection,
            RTCSessionDescription,
        )

        await self.close()

        pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        self._pc = pc
        loop = asyncio.get_event_loop()

        @pc.on("track")
        def on_track(track):
            if track.kind != "audio" or pc is not self._pc:
                return
            self._pump_task = loop.create_task(self._pump(track))

        @pc.on("icecandidate")
        def on_icecandidate(candidate):
            if candidate is None or self._on_ice is None or pc is not self._pc:
                return
            loop.create_task(
                self._on_ice(
                    candidate_to_sdp(candidate),
                    candidate.sdpMid,
                    candidate.sdpMLineIndex,
                )
            )

        @pc.on("connectionstatechange")
        def on_connectionstatechange():
            # Ignore events from a peer connection we have already replaced or
            # closed. Without this, tearing the call down flips the UI to
            # "closed"/"failed" and it stays red when the phone comes back.
            if pc is not self._pc or self._on_state is None:
                return
            loop.create_task(self._on_state(pc.connectionState))

        await pc.setRemoteDescription(RTCSessionDescription(sdp=offer_sdp, type="offer"))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        return pc.localDescription.sdp

    async def add_candidate(self, candidate, sdp_mid, sdp_m_line_index):
        if self._pc is None or not candidate:
            return
        try:
            ice = candidate_from_string(candidate, sdp_mid, sdp_m_line_index)
        except Exception as exc:
            log.debug("ignoring malformed candidate %r: %s", candidate, exc)
            return
        try:
            await self._pc.addIceCandidate(ice)
        except Exception as exc:
            log.debug("addIceCandidate failed: %s", exc)

    async def close(self):
        task, self._pump_task = self._pump_task, None
        if task is not None:
            task.cancel()

        pc, self._pc = self._pc, None
        if pc is not None:
            try:
                await pc.close()
            except Exception:
                pass

    async def _pump(self, track):
        try:
            while True:
                frame = await track.recv()
                self._on_pcm(frame_to_pcm(frame))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.debug("audio pump stopped: %s", exc)
