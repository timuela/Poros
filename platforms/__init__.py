import sys


def get_platform():
    if sys.platform == 'win32':
        from .windows import WindowsPlatform
        return WindowsPlatform()
    elif sys.platform == 'linux':
        from .linux import LinuxPlatform
        return LinuxPlatform()
    elif sys.platform == 'darwin':
        from .macos import MacOSPlatform
        return MacOSPlatform()
    else:
        raise RuntimeError(f"Unsupported operating system: {sys.platform}")
