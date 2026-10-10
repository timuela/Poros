import queue

# numpy and PortAudio are imported lazily: together they are ~0.8s of startup
# cost that only matters once audio is actually flowing. Missing PortAudio must
# not stop the app starting - opening the device reports it instead.
_np = None
_sd = None
_sd_error = ""


def _numpy():
    global _np
    if _np is None:
        import numpy
        _np = numpy
    return _np


def _sounddevice():
    global _sd, _sd_error
    if _sd is None and not _sd_error:
        try:
            import sounddevice as sd
        except Exception as exc:  # pragma: no cover - depends on the host
            _sd_error = str(exc)
        else:
            _sd = sd
    return _sd


SAMPLE_RATE = 48000
BLOCK_FRAMES = 960
QUEUE_BLOCKS = 12


class AudioOutput:
    """PortAudio output stream fed by decoded WebRTC frames.

    ``push`` is called from the asyncio thread, the stream callback runs on a
    PortAudio thread, and gain/mute are set from the Qt thread.
    """

    def __init__(self):
        self._queue = queue.Queue(maxsize=QUEUE_BLOCKS)
        self._stream = None
        self._device = None
        self._channels = 2
        self._partial = None
        self._gain = 1.0
        self._muted = False
        self._level = 0.0

    @property
    def device(self):
        return self._device

    @property
    def level(self):
        """Most recent output level, roughly 0.0 - 1.0."""
        return self._level

    def start(self, device_index):
        self.stop()

        sd = _sounddevice()
        if sd is None:
            raise RuntimeError(
                "PortAudio is not available, so audio cannot be played. "
                "On Linux install it with: sudo apt install libportaudio2"
            )

        info = sd.query_devices(device_index)
        self._channels = max(1, min(2, int(info["max_output_channels"])))
        self._device = device_index

        self._stream = sd.OutputStream(
            device=device_index,
            samplerate=SAMPLE_RATE,
            channels=self._channels,
            dtype="int16",
            blocksize=BLOCK_FRAMES,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self):
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self._device = None
        self._partial = None
        self._drain()

    def set_gain(self, gain):
        self._gain = float(gain)

    def set_muted(self, muted):
        self._muted = bool(muted)

    def push(self, pcm):
        """Queue one decoded frame, shaped (samples, channels) as int16."""
        if pcm is None or len(pcm) == 0:
            return

        np = _numpy()
        if pcm.shape[1] != self._channels:
            if pcm.shape[1] == 1:
                pcm = np.repeat(pcm, self._channels, axis=1)
            else:
                pcm = pcm[:, : self._channels]

        try:
            self._queue.put_nowait(pcm)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(pcm)
            except queue.Empty:
                pass

    def _drain(self):
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def _callback(self, outdata, frames, time_info, status):
        np = _numpy()
        written = 0
        while written < frames:
            if self._partial is None or len(self._partial) == 0:
                try:
                    self._partial = self._queue.get_nowait()
                except queue.Empty:
                    self._partial = None
                    break

            take = min(frames - written, len(self._partial))
            outdata[written : written + take] = self._partial[:take]
            self._partial = self._partial[take:]
            written += take

        if written < frames:
            outdata[written:] = 0

        block = outdata.astype(np.float32)
        self._level = float(np.sqrt(np.mean(block * block))) / 32768.0

        if self._muted:
            outdata.fill(0)
        elif self._gain != 1.0:
            scaled = outdata.astype(np.float32) * self._gain
            np.clip(scaled, -32768.0, 32767.0, out=scaled)
            outdata[:] = scaled.astype(np.int16)
