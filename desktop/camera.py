"""Video camera support for the desktop host.

Two pieces live here:

* :class:`VirtualCamera` - a thin ctypes wrapper around the bundled DirectShow
  sender filter (``virtualcam/poros-cam.dll``). Creating a camera publishes a
  system webcam that the rest of the system can pick up.
* :class:`CameraReceiver` - pulls the phone's RTSP stream and hands decoded
  BGR24 frames to a callback.

Both are Windows-only in practice; the module imports cleanly elsewhere so the
rest of the app can load it unconditionally.
"""

import ctypes
import logging
import os
import subprocess
import sys
import threading
import time

log = logging.getLogger(__name__)

# The filter is registered under this class id; keep it in sync with the build.
FILTER_CLSID = "{7B2E9C41-3A8D-4F52-9E6B-1C4A5D7E8F90}"
FILTER_NAME = "Poros Virtual Camera"
DLL_NAME = "poros-cam.dll"

# Set once a receiver has supplied these; used for the preview aspect ratio.
DEFAULT_FPS = 30

# Live-feed latency guard. When the gap between the stream clock and wall time
# passes LATENCY_LIMIT the receiver throws away everything but keyframes until
# it is back under LATENCY_RESUME, so a slow moment can never turn into a feed
# that is seconds behind.
LATENCY_LIMIT = 1.5
LATENCY_RESUME = 0.4


# ----------------------------------------------------------------------
# paths
# ----------------------------------------------------------------------
def _bundle_dir():
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "virtualcam")


def dll_path():
    return os.path.join(_bundle_dir(), DLL_NAME)


def library_available():
    return sys.platform == "win32" and os.path.exists(dll_path())


# ----------------------------------------------------------------------
# registration
# ----------------------------------------------------------------------
def registered_dll_path():
    """The DLL path stored in the registry, or None when nothing is registered."""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        key = rf"CLSID\{FILTER_CLSID}\InprocServer32"
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, key) as handle:
            return winreg.QueryValueEx(handle, "")[0]
    except OSError:
        return None
    except Exception:
        return None


def is_virtual_camera_installed():
    # A registration whose DLL has since been moved or deleted is treated as
    # absent, so the app re-registers from its own bundle when it needs to.
    path = registered_dll_path()
    return bool(path) and os.path.exists(path)


def _call_in_process(unregister):
    """Register/unregister by loading the DLL and calling its COM entry point."""
    path = dll_path()
    if not os.path.exists(path):
        return None
    try:
        dll = ctypes.WinDLL(path)
        entry = dll.DllUnregisterServer if unregister else dll.DllRegisterServer
        entry.restype = ctypes.c_long
        return int(entry())
    except Exception:
        log.debug("in-process registration failed", exc_info=True)
        return None


def _regsvr32_elevated(unregister):
    """Fall back to an elevated regsvr32, which raises the usual UAC prompt."""
    path = dll_path()
    argument = "/s " + ("/u " if unregister else "") + f'"{path}"'
    command = (
        "$p = Start-Process -FilePath 'regsvr32.exe' "
        f"-ArgumentList '{argument}' -Verb RunAs -Wait "
        "-WindowStyle Hidden -PassThru; exit $p.ExitCode"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", command],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0
    except Exception:
        log.debug("elevated regsvr32 failed", exc_info=True)
        return False


def install_virtual_camera():
    """Returns (succeeded, message)."""
    if sys.platform != "win32":
        return False, "The virtual camera is only available on Windows."
    if is_virtual_camera_installed():
        return True, ""
    if not os.path.exists(dll_path()):
        return False, f"Missing {DLL_NAME}."

    if _call_in_process(False) == 0:
        return True, ""

    if _regsvr32_elevated(False) and is_virtual_camera_installed():
        return True, ""
    return False, "Could not register the virtual camera."


def uninstall_virtual_camera():
    """Returns (succeeded, message)."""
    if sys.platform != "win32":
        return False, "The virtual camera is only available on Windows."
    if not is_virtual_camera_installed():
        return True, ""

    if _call_in_process(True) == 0 and not is_virtual_camera_installed():
        return True, ""

    if _regsvr32_elevated(True) and not is_virtual_camera_installed():
        return True, ""
    return False, "Could not unregister the virtual camera."


# ----------------------------------------------------------------------
# virtual camera (sender side)
# ----------------------------------------------------------------------
class VirtualCamera:
    """Drives the DirectShow sender filter.

    Only one camera instance can exist per machine, so :meth:`open` replaces any
    previous one.
    """

    _dll = None
    _dll_lock = threading.Lock()

    def __init__(self):
        self._handle = None
        self._width = 0
        self._height = 0
        self._lock = threading.Lock()

    @classmethod
    def _library(cls):
        if cls._dll is not None:
            return cls._dll
        with cls._dll_lock:
            if cls._dll is not None:
                return cls._dll
            path = dll_path()
            if not os.path.exists(path):
                raise RuntimeError(f"Virtual camera library not found at {path}")
            dll = ctypes.WinDLL(path)
            dll.scCreateCamera.restype = ctypes.c_void_p
            dll.scCreateCamera.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_float]
            dll.scDeleteCamera.restype = None
            dll.scDeleteCamera.argtypes = [ctypes.c_void_p]
            dll.scSendFrame.restype = None
            dll.scSendFrame.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            dll.scWaitForConnection.restype = ctypes.c_bool
            dll.scWaitForConnection.argtypes = [ctypes.c_void_p, ctypes.c_float]
            dll.scIsConnected.restype = ctypes.c_bool
            dll.scIsConnected.argtypes = [ctypes.c_void_p]
            cls._dll = dll
            return dll

    @property
    def size(self):
        return self._width, self._height

    def open(self, width, height, fps=DEFAULT_FPS, attempts=12, delay=0.15):
        """Create the camera. Dimensions are rounded to a multiple of four.

        The framerate is deliberately 0 ("real-time"): it tells the sender to
        publish every frame immediately instead of sleeping to pace them, which
        is what we want for a live webcam feed and keeps latency down.

        Only one camera can exist system-wide, and a camera that was just
        released is not always gone instantly, so retry briefly instead of
        failing with "another instance may be running".
        """
        self.close()
        width = max(4, int(width) & ~3)
        height = max(4, int(height) & ~3)
        dll = self._library()

        handle = None
        for _ in range(max(1, attempts)):
            handle = dll.scCreateCamera(width, height, ctypes.c_float(0.0))
            if handle:
                break
            time.sleep(delay)
        if not handle:
            raise RuntimeError(
                "Could not create the virtual camera - another instance may be running."
            )
        with self._lock:
            self._handle = handle
            self._width = width
            self._height = height
        return width, height

    def send(self, frame):
        """Send one BGR24 frame of exactly ``width * height * 3`` bytes.

        A contiguous numpy array is handed over by pointer - ``scSendFrame``
        copies into shared memory itself, so making our own copy first would
        just burn a full-frame memcpy (25 MB at 4K) on every single frame.
        """
        with self._lock:
            handle = self._handle
        if not handle or frame is None:
            return
        if isinstance(frame, (bytes, bytearray, memoryview)):
            buffer = (ctypes.c_ubyte * len(frame)).from_buffer_copy(frame)
            self._library().scSendFrame(handle, buffer)
        else:
            self._library().scSendFrame(handle, frame.ctypes.data_as(ctypes.c_void_p))

    def is_connected(self):
        with self._lock:
            handle = self._handle
        if not handle:
            return False
        try:
            return bool(self._library().scIsConnected(handle))
        except Exception:
            return False

    def close(self):
        with self._lock:
            handle, self._handle = self._handle, None
            self._width = self._height = 0
        if handle and self._dll is not None:
            try:
                self._dll.scDeleteCamera(handle)
            except Exception:
                log.debug("could not delete the virtual camera", exc_info=True)


# ----------------------------------------------------------------------
# RTSP receiver
# ----------------------------------------------------------------------
class CameraReceiver:
    """Decodes the phone's RTSP stream with FFmpeg and emits BGR24 frames."""

    def __init__(self, on_frame=None, on_state=None, on_stats=None):
        self._on_frame = on_frame
        self._on_state = on_state
        self._on_stats = on_stats
        self._thread = None
        self._stop = threading.Event()
        self._rotation = 0

    def start(self, url, width, height, transport="tcp", rotation=0):
        self.stop()
        self._rotation = int(rotation) % 360
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(url, int(width), int(height), transport),
            name="poros-video",
            daemon=True,
        )
        self._thread.start()

    def set_rotation(self, degrees):
        """Change the output rotation; the receive loop picks it up."""
        self._rotation = int(degrees) % 360

    def stop(self):
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            # The thread unblocks within a frame; a stalled socket is left to
            # the daemon flag rather than hanging the UI on shutdown.
            thread.join(timeout=1.5)

    @property
    def running(self):
        thread = self._thread
        return thread is not None and thread.is_alive()

    def _notify(self, state, detail=""):
        if self._on_state is not None:
            try:
                self._on_state(state, detail)
            except Exception:
                log.debug("camera state callback failed", exc_info=True)

    def _stats(self, sample):
        if self._on_stats is not None:
            try:
                self._on_stats(sample)
            except Exception:
                log.debug("camera stats callback failed", exc_info=True)

    def _run(self, url, width, height, transport):
        try:
            import av
            import numpy as np
        except Exception as exc:
            self._notify("error", f"FFmpeg bindings unavailable: {exc}")
            return

        options = {
            # TCP is reliable; UDP is lighter but drops packets, which shows up
            # as smearing, so it needs a bigger socket buffer to absorb bursts.
            "rtsp_transport": transport,
            "flags": "low_delay",
            "probesize": "32768",
            "analyzeduration": "1000000",
            # Bound the socket so an unreachable or stalled stream fails and is
            # retried instead of wedging the receive thread (microseconds).
            "timeout": "5000000",
        }
        if transport == "udp":
            # UDP never retransmits, so give the kernel room to hold a burst
            # rather than discarding packets the moment the reader is busy.
            options["buffer_size"] = "4194304"
        else:
            # TCP retransmits, so the only risk is buffering we cannot drain:
            # keep the demuxer's own queues minimal.
            options["max_delay"] = "0"
            options["reorder_queue_size"] = "0"

        self._notify("connecting")
        while not self._stop.is_set():
            try:
                container = av.open(url, options=options)
            except Exception as exc:
                if self._stop.is_set():
                    break
                self._notify("error", str(exc))
                self._stop.wait(1.0)
                continue

            try:
                stream = container.streams.video[0]
                # Slice threading parallelises inside a frame instead of across
                # frames, so it is both faster here and adds no output delay -
                # frame threading would hold back several frames of latency.
                stream.thread_type = "SLICE"
                self._notify("streaming")

                # Rotation goes through FFmpeg's transpose filter rather than
                # numpy: transposing a 1080p frame in numpy costs ~9 ms, which
                # on its own pushes 60 fps over budget - and with TCP the frames
                # we then fail to drain turn into growing lag.
                graph = None
                graph_source = None
                graph_sink = None
                graph_rotation = None

                def build_graph(rotation):
                    built = av.filter.Graph()
                    node = built.add_buffer(template=stream)
                    head = node

                    def chain(name, args=None):
                        nonlocal node
                        added = built.add(name) if args is None else built.add(name, args)
                        node.link_to(added)
                        node = added

                    # Scale and rotate in the decoder's own format; converting
                    # to RGB first would push three bytes per pixel through the
                    # transpose instead of fewer.
                    chain("scale", f"{width}:{height}")
                    if rotation == 90:
                        chain("transpose", "clock")
                    elif rotation == 270:
                        chain("transpose", "cclock")
                    elif rotation == 180:
                        chain("hflip")
                        chain("vflip")
                    chain("format", "bgr24")

                    tail = built.add("buffersink")
                    node.link_to(tail)
                    built.configure()
                    return built, head, tail

                window_start = time.monotonic()
                frames = 0
                payload = 0
                dropped = 0
                process_time = 0.0
                source_size = (0, 0)
                reported = False

                # Latency tracking: the gap between the stream's own clock and
                # wall time. If the decoder falls behind the phone, this grows -
                # and with TCP a growing lag never recovers on its own.
                anchor_wall = None
                anchor_media = None
                latency = 0.0
                catching_up = False

                for packet in container.demux(stream):
                    if self._stop.is_set():
                        break
                    payload += packet.size

                    # When too far behind, skip everything but keyframes: that
                    # drains the socket at full speed and drops stale frames
                    # instead of showing a picture that is seconds old.
                    if catching_up and not packet.is_keyframe:
                        dropped += 1
                        continue

                    for frame in packet.decode():
                        if self._stop.is_set():
                            break

                        if anchor_wall is None:
                            anchor_wall = time.monotonic()
                            anchor_media = frame.time if frame.time is not None else 0.0
                        if frame.time is not None:
                            latency = (time.monotonic() - anchor_wall) - (
                                frame.time - anchor_media
                            )

                        if latency > LATENCY_LIMIT:
                            catching_up = True
                        elif catching_up and latency < LATENCY_RESUME:
                            catching_up = False

                        if catching_up:
                            dropped += 1
                            continue

                        if not reported:
                            # Report the size the phone actually encodes, which
                            # is not necessarily the size that was requested.
                            reported = True
                            source_size = (frame.width, frame.height)
                            self._notify(
                                "streaming", f"{frame.width}x{frame.height}"
                            )

                        began = time.perf_counter()
                        rotation = self._rotation
                        if rotation:
                            if graph is None or graph_rotation != rotation:
                                graph, graph_source, graph_sink = build_graph(rotation)
                                graph_rotation = rotation
                            array = None
                            graph_source.push(frame)
                            while True:
                                try:
                                    produced = graph_sink.pull()
                                except Exception:
                                    break
                                array = produced.to_ndarray()
                                break
                            if array is None:
                                continue
                        else:
                            image = frame.reformat(
                                width=width, height=height, format="bgr24"
                            )
                            array = image.to_ndarray()
                        # to_ndarray usually hands back a contiguous view, in
                        # which case this is free; it only copies if a frame
                        # ever arrives with padded rows.
                        if not array.flags["C_CONTIGUOUS"]:
                            array = np.ascontiguousarray(array)
                        self._on_frame(array)
                        process_time += time.perf_counter() - began
                        frames += 1

                    now = time.monotonic()
                    elapsed = now - window_start
                    if elapsed >= 1.0:
                        self._stats(
                            {
                                "width": source_size[0],
                                "height": source_size[1],
                                "fps": frames / elapsed,
                                "mbps": payload * 8 / elapsed / 1_000_000,
                                "ms": (process_time / frames * 1000) if frames else 0.0,
                                "latency": max(0.0, latency),
                                "dropped": dropped,
                            }
                        )
                        window_start = now
                        frames = 0
                        payload = 0
                        dropped = 0
                        process_time = 0.0
            except Exception as exc:
                if not self._stop.is_set():
                    log.debug("video decode error: %s", exc)
                    self._notify("error", str(exc))
            finally:
                try:
                    container.close()
                except Exception:
                    pass

            if self._stop.is_set():
                break
            self._notify("reconnecting")
            self._stop.wait(0.5)

        self._notify("stopped")
