"""Windows run-at-login helpers.

Backed by the per-user Run key, which works for both the portable exe and an
installed one, and is the same value the installer's "start with Windows" task
writes. Everything is a no-op off Windows.
"""

import os
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Poros"
INSTALL_KEY = r"Software\Poros"


def _command():
    exe = sys.executable
    if getattr(sys, "frozen", False):
        return f'"{exe}"'
    # Running from source: prefer pythonw so no console flashes up at login.
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pythonw):
        exe = pythonw
    main = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py"
    )
    return f'"{exe}" "{main}"'


def is_enabled():
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except OSError:
        return False


def set_enabled(enabled):
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def installed_app_id():
    """The AppUserModelID the installer registered, or None when portable."""
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INSTALL_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "AppUserModelID")
        return str(value) or None
    except OSError:
        return None
