import os
import subprocess
import re
from .base import BasePlatform

class LinuxPlatform(BasePlatform):
    SINK_NAME = 'poros_sink'
    SINK_DESCRIPTION = 'Poros Virtual Output'

    @property
    def driver_display_name(self) -> str:
        return f'{self.SINK_DESCRIPTION} Monitor'

    @property
    def driver_match_keyword(self) -> str:
        return self.SINK_NAME

    def list_lan_ips(self) -> list[str]:
        """Every IPv4 address, including virtual adapters such as VPN / Tailscale."""
        ips: list[str] = []
        try:
            output = subprocess.check_output(
                ['ip', '-o', '-4', 'addr', 'show'], text=True, timeout=5
            )
            for line in output.splitlines():
                parts = line.split()
                if len(parts) >= 4:
                    address = parts[3].split('/')[0]
                    if not address.startswith(('127.', '169.254.')):
                        ips.append(address)
            return ips
        except Exception:
            pass

        try:
            output = subprocess.check_output(
                ['hostname', '-I'], text=True, timeout=5
            )
            return [
                a for a in output.split()
                if not a.startswith(('127.', '169.254.'))
            ]
        except Exception as e:
            print("List LAN IPs Error:", e)
            return []

    def is_admin(self) -> bool:
        try:
            return True
        except AttributeError:
            return False

    def _run_pactl(self, *args) -> tuple[int, str, str]:
        """Run pactl, returning (returncode, stdout, stderr)."""
        try:
            proc = subprocess.run(
                ['pactl', *args],
                capture_output=True, text=True, timeout=10
            )
            return proc.returncode, proc.stdout, proc.stderr
        except FileNotFoundError:
            return -1, '', self._msg(
                "pactl_missing",
                'pactl is not available; check that PulseAudio/PipeWire is installed.',
            )
        except subprocess.TimeoutExpired:
            return -1, '', self._msg("pactl_timeout", 'pactl timed out.')

    def _get_module_id(self) -> int | None:
        """Id of the loaded poros null-sink module, if there is one."""
        code, stdout, _ = self._run_pactl('list', 'modules', 'short')
        if code != 0:
            return None
        for line in stdout.splitlines():
            if f'sink_name={self.SINK_NAME}' in line:
                m = re.match(r'(\d+)', line)
                if m:
                    return int(m.group(1))
        return None

    def is_driver_installed(self) -> bool:
        return self._get_module_id() is not None

    def install_driver(self) -> tuple[bool, str]:
        if self.is_driver_installed():
            return True, self._msg(
                "driver_ready", 'The virtual audio device is already set up.'
            )

        code, stdout, stderr = self._run_pactl(
            'load-module', 'module-null-sink',
            f'sink_name={self.SINK_NAME}',
            f'sink_properties=device.description={self.SINK_DESCRIPTION}'
        )
        if code == 0:
            return True, self._msg("driver_created", 'Virtual audio device created.')
        return False, self._msg(
            "driver_create_failed",
            'Could not create the virtual audio device:\n{detail}',
            detail=stderr,
        )

    def uninstall_driver(self) -> tuple[bool, str]:
        module_id = self._get_module_id()
        if module_id is None:
            return False, self._msg(
                "driver_missing", 'No Poros virtual audio device found.'
            )

        code, stdout, stderr = self._run_pactl('unload-module', str(module_id))
        if code == 0:
            return True, self._msg("driver_removed", 'Virtual audio device removed.')
        return False, self._msg(
            "driver_remove_failed",
            'Could not remove the virtual audio device:\n{detail}',
            detail=stderr,
        )

    def get_post_install_warning(self) -> str:
        return self._msg(
            "driver_post_install",
            'The virtual audio device is ready.\n\n'
            'In games or meeting apps, set the microphone device to:\n'
            '"{device}"\n\n'
            'If it does not appear, reopen the app you were using.',
            device=f'{self.SINK_DESCRIPTION} Monitor',
        )
