"""Unit tests for platform providers — Linux and Windows.

All OS-specific calls (subprocess, shutil.which, file reads) are mocked
so these tests run on any host OS without side effects.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest


# ── LinuxPlatform ─────────────────────────────────────────────────────────────

class TestLinuxPlatform:

    @pytest.fixture()
    def platform_debian(self):
        from esplay.platform.linux import LinuxPlatform
        with patch("esplay.platform.linux._read_os_release", return_value={
            "ID": "ubuntu",
            "ID_LIKE": "debian",
            "PRETTY_NAME": "Ubuntu 24.04 LTS",
            "VERSION_CODENAME": "noble",
        }):
            p = LinuxPlatform()
        return p

    @pytest.fixture()
    def platform_fedora(self):
        from esplay.platform.linux import LinuxPlatform
        with patch("esplay.platform.linux._read_os_release", return_value={
            "ID": "fedora",
            "ID_LIKE": "",
            "PRETTY_NAME": "Fedora Linux 40",
        }):
            p = LinuxPlatform()
        return p

    @pytest.fixture()
    def platform_arch(self):
        from esplay.platform.linux import LinuxPlatform
        with patch("esplay.platform.linux._read_os_release", return_value={
            "ID": "arch",
            "ID_LIKE": "",
            "PRETTY_NAME": "Arch Linux",
        }):
            p = LinuxPlatform()
        return p

    @pytest.fixture()
    def platform_suse(self):
        from esplay.platform.linux import LinuxPlatform
        with patch("esplay.platform.linux._read_os_release", return_value={
            "ID": "opensuse-leap",
            "ID_LIKE": "suse",
            "PRETTY_NAME": "openSUSE Leap 15.6",
        }):
            p = LinuxPlatform()
        return p

    # name()
    def test_name_includes_pretty_name(self, platform_debian):
        assert "Ubuntu 24.04" in platform_debian.name()

    def test_name_fallback(self):
        from esplay.platform.linux import LinuxPlatform
        with patch("esplay.platform.linux._read_os_release", return_value={}):
            p = LinuxPlatform()
        assert p.name() == "Linux"

    # is_docker_installed()
    def test_is_docker_installed_true(self, platform_debian):
        with patch("esplay.platform.linux.shutil.which", return_value="/usr/bin/docker"):
            assert platform_debian.is_docker_installed() is True

    def test_is_docker_installed_false(self, platform_debian):
        with patch("esplay.platform.linux.shutil.which", return_value=None):
            assert platform_debian.is_docker_installed() is False

    # install_docker_instructions()
    def test_instructions_debian_mention_apt(self, platform_debian):
        instructions = platform_debian.install_docker_instructions()
        assert "apt-get" in instructions

    def test_instructions_fedora_mention_dnf(self, platform_fedora):
        instructions = platform_fedora.install_docker_instructions()
        assert "dnf" in instructions

    def test_instructions_arch_mention_pacman(self, platform_arch):
        instructions = platform_arch.install_docker_instructions()
        assert "pacman" in instructions

    def test_instructions_suse_mention_zypper(self, platform_suse):
        instructions = platform_suse.install_docker_instructions()
        assert "zypper" in instructions

    # offer_docker_install()
    def test_offer_install_returns_false_on_decline(self, platform_debian):
        with patch("questionary.confirm") as mock_confirm:
            mock_confirm.return_value.ask.return_value = False
            result = platform_debian.offer_docker_install()
        assert result is False

    def test_offer_install_runs_apt_commands_on_debian(self, platform_debian):
        with (
            patch("questionary.confirm") as mock_confirm,
            patch("esplay.platform.linux.subprocess.run") as mock_run,
            patch("esplay.platform.linux.shutil.which", return_value="/usr/bin/docker"),
        ):
            mock_confirm.return_value.ask.return_value = True
            mock_run.return_value = MagicMock(returncode=0)
            result = platform_debian.offer_docker_install()

        assert result is True
        called_cmds = [call.args[0] for call in mock_run.call_args_list]
        assert any("apt-get" in " ".join(cmd) for cmd in called_cmds)

    def test_offer_install_returns_false_on_unknown_distro(self):
        from esplay.platform.linux import LinuxPlatform
        with patch("esplay.platform.linux._read_os_release", return_value={
            "ID": "void",
            "ID_LIKE": "",
            "PRETTY_NAME": "Void Linux",
        }):
            p = LinuxPlatform()
        result = p.offer_docker_install()
        assert result is False

    # open_url()
    def test_open_url_uses_xdg_open_when_available(self, platform_debian):
        with (
            patch("esplay.platform.linux.shutil.which", return_value="/usr/bin/xdg-open"),
            patch("esplay.platform.linux.subprocess.Popen") as mock_popen,
        ):
            platform_debian.open_url("http://localhost:5601")
        mock_popen.assert_called_once_with(["xdg-open", "http://localhost:5601"])

    def test_open_url_falls_back_to_webbrowser(self, platform_debian):
        with (
            patch("esplay.platform.linux.shutil.which", return_value=None),
            patch("esplay.platform.linux.webbrowser.open") as mock_wb,
        ):
            platform_debian.open_url("http://localhost:5601")
        mock_wb.assert_called_once_with("http://localhost:5601")

    # distro detection
    def test_distro_detection_debian(self):
        from esplay.platform.linux import _detect_distro_family
        with patch("esplay.platform.linux._read_os_release", return_value={
            "ID": "ubuntu", "ID_LIKE": "debian",
        }):
            assert _detect_distro_family() == "debian"

    def test_distro_detection_rhel_like(self):
        from esplay.platform.linux import _detect_distro_family
        with patch("esplay.platform.linux._read_os_release", return_value={
            "ID": "rocky", "ID_LIKE": "rhel centos fedora",
        }):
            assert _detect_distro_family() == "fedora"

    def test_distro_detection_unknown(self):
        from esplay.platform.linux import _detect_distro_family
        with patch("esplay.platform.linux._read_os_release", return_value={
            "ID": "gentoo", "ID_LIKE": "",
        }):
            assert _detect_distro_family() == "unknown"


# ── WindowsPlatform ───────────────────────────────────────────────────────────

class TestWindowsPlatform:

    @pytest.fixture()
    def win_platform(self):
        from esplay.platform.windows import WindowsPlatform
        return WindowsPlatform()

    # name()
    def test_name_contains_windows(self, win_platform):
        with patch("platform.version", return_value="10.0.22621"), \
             patch("platform.release", return_value="11"):
            assert "Windows" in win_platform.name()

    # is_docker_installed()
    def test_is_docker_installed_true(self, win_platform):
        with patch("esplay.platform.windows.shutil.which", return_value=r"C:\Program Files\Docker\docker.exe"):
            assert win_platform.is_docker_installed() is True

    def test_is_docker_installed_false(self, win_platform):
        with patch("esplay.platform.windows.shutil.which", return_value=None):
            assert win_platform.is_docker_installed() is False

    # install_docker_instructions()
    def test_instructions_mention_winget(self, win_platform):
        assert "winget" in win_platform.install_docker_instructions()

    def test_instructions_mention_wsl(self, win_platform):
        assert "WSL" in win_platform.install_docker_instructions()

    def test_instructions_mention_chocolatey(self, win_platform):
        assert "choco" in win_platform.install_docker_instructions()

    # offer_docker_install() — winget path
    def test_offer_install_uses_winget_when_available(self, win_platform):
        with (
            patch("esplay.platform.windows._winget_available", return_value=True),
            patch("esplay.platform.windows._choco_available", return_value=False),
            patch("questionary.confirm") as mock_confirm,
            patch("esplay.platform.windows.subprocess.run") as mock_run,
            patch("esplay.platform.windows.shutil.which", return_value=r"C:\Program Files\Docker\docker.exe"),
            patch.object(win_platform, "_try_launch_docker_desktop"),
        ):
            mock_confirm.return_value.ask.return_value = True
            mock_run.return_value = MagicMock(returncode=0)
            result = win_platform.offer_docker_install()

        assert result is True
        cmd = mock_run.call_args.args[0]
        assert "winget" in cmd

    def test_offer_install_falls_back_to_choco(self, win_platform):
        with (
            patch("esplay.platform.windows._winget_available", return_value=False),
            patch("esplay.platform.windows._choco_available", return_value=True),
            patch("questionary.confirm") as mock_confirm,
            patch("esplay.platform.windows.subprocess.run") as mock_run,
            patch("esplay.platform.windows.shutil.which", return_value=r"C:\Program Files\Docker\docker.exe"),
            patch.object(win_platform, "_try_launch_docker_desktop"),
        ):
            mock_confirm.return_value.ask.return_value = True
            mock_run.return_value = MagicMock(returncode=0)
            result = win_platform.offer_docker_install()

        assert result is True
        cmd = mock_run.call_args.args[0]
        assert "choco" in cmd

    def test_offer_install_returns_false_when_no_pkg_manager(self, win_platform):
        with (
            patch("esplay.platform.windows._winget_available", return_value=False),
            patch("esplay.platform.windows._choco_available", return_value=False),
        ):
            result = win_platform.offer_docker_install()
        assert result is False

    def test_offer_install_returns_false_on_decline(self, win_platform):
        with (
            patch("esplay.platform.windows._winget_available", return_value=True),
            patch("questionary.confirm") as mock_confirm,
        ):
            mock_confirm.return_value.ask.return_value = False
            result = win_platform.offer_docker_install()
        assert result is False

    # open_url()
    def test_open_url_uses_os_startfile(self, win_platform):
        # create=True because os.startfile only exists on Windows.
        with patch("esplay.platform.windows.os.startfile", create=True) as mock_sf:
            win_platform.open_url("http://localhost:5601")
        mock_sf.assert_called_once_with("http://localhost:5601")

    def test_open_url_falls_back_to_webbrowser_if_no_startfile(self, win_platform):
        # Simulate non-Windows where os.startfile raises AttributeError.
        with (
            patch("esplay.platform.windows.os.startfile", create=True, side_effect=AttributeError),
            patch("esplay.platform.windows.webbrowser.open") as mock_wb,
        ):
            win_platform.open_url("http://localhost:5601")
        mock_wb.assert_called_once_with("http://localhost:5601")


# ── PlatformFactory ───────────────────────────────────────────────────────────

class TestPlatformFactory:

    def test_factory_returns_macos_on_darwin(self):
        from esplay.platform.factory import PlatformFactory
        from esplay.platform.macos import MacOSPlatform
        with patch("platform.system", return_value="Darwin"):
            p = PlatformFactory.get()
        assert isinstance(p, MacOSPlatform)

    def test_factory_returns_linux_on_linux(self):
        from esplay.platform.factory import PlatformFactory
        from esplay.platform.linux import LinuxPlatform
        with (
            patch("platform.system", return_value="Linux"),
            patch("esplay.platform.linux._read_os_release", return_value={
                "ID": "ubuntu", "ID_LIKE": "debian", "PRETTY_NAME": "Ubuntu 24.04",
            }),
        ):
            p = PlatformFactory.get()
        assert isinstance(p, LinuxPlatform)

    def test_factory_returns_windows_on_windows(self):
        from esplay.platform.factory import PlatformFactory
        from esplay.platform.windows import WindowsPlatform
        with patch("platform.system", return_value="Windows"):
            p = PlatformFactory.get()
        assert isinstance(p, WindowsPlatform)

    def test_factory_raises_on_unsupported_os(self):
        from esplay.errors import UnsupportedPlatformError
        from esplay.platform.factory import PlatformFactory
        with (
            patch("platform.system", return_value="FreeBSD"),
            pytest.raises(UnsupportedPlatformError),
        ):
            PlatformFactory.get()
