def translate(t, key, fallback, **params):
    """Look a message up in the current language, then fill in {placeholders}."""
    text = fallback
    if t is not None:
        try:
            text = t(key, fallback)
        except Exception:
            text = fallback
    for name, value in params.items():
        text = text.replace("{" + name + "}", str(value))
    return text


class BasePlatform:
    """Abstract base class for a platform, defining what each one must provide."""

    def __init__(self):
        self._t = None

    def set_translator(self, translate_func):
        """The desktop app installs one so driver messages follow the UI language."""
        self._t = translate_func

    def _msg(self, key, fallback, **params):
        return translate(self._t, key, fallback, **params)

    @property
    def driver_display_name(self) -> str:
        """Name of the virtual device shown in the front-end UI."""
        raise NotImplementedError

    @property
    def driver_match_keyword(self) -> str:
        """Lower-case keyword used to match the device in enumerateDevices."""
        raise NotImplementedError

    def list_lan_ips(self) -> list[str]:
        """Every usable LAN IPv4 address on this host (for the access URLs)."""
        return []

    def is_admin(self) -> bool:
        raise NotImplementedError

    def is_driver_installed(self) -> bool:
        raise NotImplementedError

    def install_driver(self) -> tuple[bool, str]:
        """Returns (succeeded, message)."""
        raise NotImplementedError

    def uninstall_driver(self) -> tuple[bool, str]:
        """Returns (succeeded, message)."""
        raise NotImplementedError

    def get_post_install_warning(self) -> str:
        """Reminder shown after the driver is installed."""
        return ""
