import os
import subprocess
from .base import BasePlatform


class MacOSPlatform(BasePlatform):
    @property
    def driver_display_name(self) -> str:
        return 'BlackHole 2ch'

    @property
    def driver_match_keyword(self) -> str:
        return 'blackhole'

    def list_lan_ips(self) -> list[str]:
        """Every IPv4 address, including virtual adapters such as VPN / Tailscale."""
        ips: list[str] = []
        try:
            output = subprocess.check_output(['ifconfig'], text=True, timeout=5)
        except Exception as e:
            print("List LAN IPs Error:", e)
            return ips

        for line in output.splitlines():
            line = line.strip()
            if not line.startswith('inet '):
                continue
            address = line.split()[1]
            if not address.startswith(('127.', '169.254.')):
                ips.append(address)
        return ips

    def is_admin(self) -> bool:
        try:
            return True
        except AttributeError:
            return False

    def is_driver_installed(self) -> bool:
        try:
            result = subprocess.run(
                ['system_profiler', 'SPAudioDataType'],
                capture_output=True, text=True, timeout=10
            )
            return 'BlackHole' in result.stdout
        except Exception:
            return False

    def install_driver(self) -> tuple[bool, str]:
        if self.is_driver_installed():
            return True, self._msg(
                "driver_ready", 'The virtual audio device is already set up.'
            )

        return False, self._msg(
            "driver_manual_install",
            'Install BlackHole manually:\n'
            'brew install blackhole-2ch\n'
            'or download it from https://github.com/ExistentialAudio/BlackHole',
        )

    def uninstall_driver(self) -> tuple[bool, str]:
        return False, self._msg(
            "driver_manual_uninstall",
            'Remove BlackHole manually:\nbrew uninstall blackhole-2ch',
        )

    def get_post_install_warning(self) -> str:
        return self._msg(
            "driver_post_install",
            'The virtual audio device is ready.\n\n'
            'In games or meeting apps, set the microphone device to:\n'
            '"{device}"\n\n'
            'If it does not appear, reopen the app you were using.',
            device='BlackHole 2ch',
        )
