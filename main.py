import os
import sys
import socket
import threading
import time
import secrets

from flask import Flask, send_from_directory, jsonify, request
from flask_socketio import SocketIO, emit

from platforms import get_platform

# Resource path resolution that also works under PyInstaller
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

# Constants
VERSION = "v0.3.6"
DEFAULT_PORT = 5000

# Single-instance detection
MUTEX_NAME = r'Local\PorosSingleInstance'
LOCK_FILENAME = 'poros.lock'
ERROR_ALREADY_EXISTS = 183
_instance_lock = None


def acquire_instance_lock():
    """Try to become the only running instance.

    Returns True when startup may continue, False when another instance is
    already running. A failure in the check itself never blocks startup.
    """
    global _instance_lock
    try:
        if sys.platform == 'win32':
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
            if not handle:
                return True
            if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
                kernel32.CloseHandle(handle)
                return False
            _instance_lock = handle
            return True

        import fcntl
        import tempfile

        path = os.path.join(tempfile.gettempdir(), LOCK_FILENAME)
        handle = open(path, 'w')
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        _instance_lock = handle
        return True
    except Exception:
        return True


def notify_already_running():
    message = 'Poros is already running.'
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, 'Poros', 0x00000040)
            return
        except Exception:
            pass
    print(f'[Poros] {message}')


def get_available_port(start_port, max_port=5100):
    for port in range(start_port, max_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('0.0.0.0', port))
                return port
            except OSError:
                continue
    return start_port

SERVER_PORT = get_available_port(DEFAULT_PORT)

# The port actually in use; the desktop client can change it
server_port = SERVER_PORT

# One-off PIN regenerated when the server starts; a phone must supply it to join
server_pin = ""
# The PIN the user chose in settings. The server starts on a worker thread while
# the UI applies this, so without it a freshly generated random PIN could
# overwrite the chosen one.
custom_pin = ""
require_pin = True


def _generate_pin():
    return f"{secrets.randbelow(1_000_000):06d}"


# Platform detection
platform = get_platform()

# ==========================================
# 1. Flask & SocketIO setup
# ==========================================
WEBUI_DIR = os.path.join(base_path, 'webui')
app = Flask(__name__, static_folder=WEBUI_DIR, static_url_path='')
app.config['SECRET_KEY'] = 'poros-super-secret-key'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')


def get_lan_ip():
    """The host's IPv4 address on the local network."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP


def get_lan_ips():
    """Every reachable IPv4 address, with the primary one first."""
    try:
        ips = [ip for ip in platform.list_lan_ips() if ip]
    except Exception:
        ips = []

    primary = get_lan_ip()
    ips = [ip for ip in ips if ip != primary]
    return [primary] + ips


# ==========================================
# 2. Routes
# ==========================================
@app.route('/')
def index():
    return send_from_directory(WEBUI_DIR, 'index.html')


@app.route('/desktop')
def desktop():
    return send_from_directory(WEBUI_DIR, 'desktop.html')


@app.route('/api/info')
def api_info():
    return jsonify({
        "ip": get_lan_ip(),
        "ips": get_lan_ips(),
        "port": server_port,
        "version": VERSION
    })


@app.route('/api/platform_info')
def api_platform_info():
    return jsonify({
        "os": sys.platform,
        "driver_display_name": platform.driver_display_name,
        "driver_match_keyword": platform.driver_match_keyword,
        "post_install_warning": platform.get_post_install_warning(),
    })


@app.route('/api/check_driver', methods=['GET'])
def api_check_driver():
    return jsonify({"installed": platform.is_driver_installed()})


@app.route('/api/install_driver', methods=['POST'])
def api_install_driver():
    success, msg = platform.install_driver()
    return jsonify({"success": success, "msg": msg})


@app.route('/api/uninstall_driver', methods=['POST'])
def api_uninstall_driver():
    success, msg = platform.uninstall_driver()
    return jsonify({"success": success, "msg": msg})


@app.route('/api/exit', methods=['POST'])
def api_exit():
    def kill_me():
        time.sleep(1)
        os._exit(0)
    threading.Thread(target=kill_me).start()
    return jsonify({"success": True})


tray_update_callback = None
is_muted = False
tray_force_update_callback = None

@app.route('/api/set_lang', methods=['POST'])
def api_set_lang():
    data = request.json or {}
    lang = data.get('lang', 'en_us')
    if tray_update_callback:
        tray_update_callback(lang)
    return jsonify({"success": True})

@app.route('/api/sync_mute', methods=['POST'])
def api_sync_mute():
    global is_muted
    data = request.json or {}
    is_muted = data.get('muted', False)
    if tray_force_update_callback:
        tray_force_update_callback()
    return jsonify({"success": True})


# ==========================================
# 3. WebRTC signalling server (Socket.IO)
# ==========================================
clients = {}  # sid -> role


def _presence_payload():
    roles = set(clients.values())
    return {
        'mobile': 'mobile' in roles,
        'desktop': 'desktop' in roles,
    }


def _broadcast_presence():
    socketio.emit('presence', _presence_payload())


@socketio.on('join')
def on_join(data):
    role = data.get('role', 'unknown') if isinstance(data, dict) else 'unknown'
    if role == 'mobile' and require_pin:
        supplied = str(data.get('pin', '')).strip() if isinstance(data, dict) else ''
        if supplied != server_pin:
            print(f"[mobile] PIN check failed (sid={request.sid})")
            emit('auth_failed', {'reason': 'pin'})
            return
    clients[request.sid] = role
    print(f"[{role}] connected to the signalling server (sid={request.sid})")
    emit('ready', {'role': role}, broadcast=True, include_self=False)
    _broadcast_presence()


@socketio.on('disconnect')
def on_disconnect():
    role = clients.pop(request.sid, None)
    if role is not None:
        print(f"[{role}] disconnected (sid={request.sid})")
        _broadcast_presence()


@socketio.on('offer')
def on_offer(data):
    emit('offer', data, broadcast=True, include_self=False)


@socketio.on('answer')
def on_answer(data):
    emit('answer', data, broadcast=True, include_self=False)


@socketio.on('ice_candidate')
def on_ice_candidate(data):
    emit('ice_candidate', data, broadcast=True, include_self=False)


@socketio.on('toggle_mute')
def on_toggle_mute():
    emit('toggle_mute', broadcast=True, include_self=False)


# Camera events: the phone announces its camera, the desktop asks it to start
# or stop, and both sides relay short control commands. Video itself never
# passes through here - it is a direct RTSP stream between phone and desktop.
@socketio.on('camera_descriptor')
def on_camera_descriptor(data):
    emit('camera_descriptor', data, broadcast=True, include_self=False)


@socketio.on('camera_status')
def on_camera_status(data):
    emit('camera_status', data, broadcast=True, include_self=False)


@socketio.on('camera_start')
def on_camera_start(data):
    emit('camera_start', data, broadcast=True, include_self=False)


@socketio.on('camera_stop')
def on_camera_stop(data):
    emit('camera_stop', data, broadcast=True, include_self=False)


@socketio.on('camera_command')
def on_camera_command(data):
    emit('camera_command', data, broadcast=True, include_self=False)


# ==========================================
# 4. Entry point
# ==========================================
_server = None
_server_lock = threading.Lock()


def _stop_server_locked():
    global _server
    server, _server = _server, None
    if server is not None:
        try:
            server.shutdown()
        except Exception:
            pass


def stop_server():
    with _server_lock:
        _stop_server_locked()


def start_server(port):
    """Start the HTTPS signalling server, stopping any running instance first.

    :raises OSError: the caller decides how to report problems such as the port
        already being in use.
    """
    global _server, server_port, server_pin
    # Imported here rather than at module load, so the TLS/ad-hoc stack is not
    # on the startup path; PyInstaller still sees them and bundles them.
    import OpenSSL  # noqa: F401 - keeps the adhoc SSL deps in the bundle
    import cryptography  # noqa: F401
    from werkzeug.serving import make_server

    with _server_lock:
        _stop_server_locked()
        _server = make_server(
            '0.0.0.0', port, app, ssl_context='adhoc', threaded=True
        )
        server_port = port
        # Keep the PIN the window is already showing. The server starts on a
        # worker thread, so it usually lands *after* the UI has picked one;
        # regenerating here would silently invalidate the code on screen and
        # the phone would be rejected with a PIN error.
        server_pin = custom_pin or server_pin or _generate_pin()

    threading.Thread(target=_server.serve_forever, daemon=True).start()

    print("\n=========================================")
    print("Poros Host started.")
    for address in get_lan_ips():
        print(f"Open this on your phone: https://{address}:{port}")
    print("=========================================\n")
    return True


def _start_server_quietly(port):
    try:
        start_server(port)
    except Exception as exc:
        print(f"[Poros] Could not start the server: {exc}")


class ServerControl:
    """Minimal server control surface exposed to the desktop client."""

    @property
    def port(self):
        return server_port

    @property
    def pin(self):
        return server_pin

    @property
    def require_pin(self):
        return require_pin

    def set_require_pin(self, enabled):
        global require_pin, server_pin
        require_pin = bool(enabled)
        if require_pin and not server_pin:
            server_pin = _generate_pin()

    def regenerate_pin(self):
        global server_pin, custom_pin
        custom_pin = ""
        server_pin = _generate_pin()
        return server_pin

    def set_pin(self, value):
        """Use a user-chosen PIN; empty means "no preference", not "new PIN"."""
        global server_pin, custom_pin
        value = str(value).strip()
        custom_pin = value
        if value:
            server_pin = value
        elif not server_pin:
            server_pin = _generate_pin()
        return server_pin

    def ips(self):
        return get_lan_ips()

    def restart(self, port):
        try:
            start_server(port)
            return True, ""
        except Exception as exc:
            return False, str(exc)


if __name__ == '__main__':
    if not acquire_instance_lock():
        notify_already_running()
        sys.exit(0)

    # Bring the server up on a worker thread so the window is on screen first:
    # the ad-hoc certificate takes a moment, and doing this on the UI thread
    # right after showing the window is what used to blank the taskbar icon.
    threading.Thread(
        target=_start_server_quietly, args=(server_port,), daemon=True
    ).start()

    icon_path = None
    for icon_rel in ('desktop/icon.png', 'icon.png', 'icon.ico', 'icon.icns'):
        candidate = os.path.join(base_path, *icon_rel.split('/'))
        if os.path.exists(candidate):
            icon_path = candidate
            break

    from desktop.app import run_desktop

    run_desktop(
        platform=platform,
        version=VERSION,
        webui_dir=WEBUI_DIR,
        icon_path=icon_path,
        server=ServerControl(),
    )

