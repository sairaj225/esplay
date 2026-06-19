"""WindowsPlatform — PlatformProvider implementation for Windows.

Install strategy (tried in order):
  1. winget  (built-in since Windows 10 21H1 / Windows 11)
  2. Chocolatey  (popular community package manager)
  3. Manual instructions (direct download link)

Docker Desktop for Windows requires either WSL 2 (recommended) or Hyper-V.
Both are noted in the instructions.

NOTE: esplay's shell commands run via subprocess — they work in both
PowerShell and Command Prompt on Windows.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import webbrowser


from esplay.platform.base import PlatformProvider


def _winget_available() -> bool:
    return shutil.which("winget") is not None


def _choco_available() -> bool:
    return shutil.which("choco") is not None


class WindowsPlatform(PlatformProvider):
    """Windows PlatformProvider supporting winget, Chocolatey, and manual install."""

    def name(self) -> str:
        # platform.version() gives something like "10.0.22621" on Windows 11.
        try:
            import platform  # noqa: PLC0415
            ver = platform.version()
            release = platform.release()
            return f"Windows {release} ({ver})"
        except Exception:
            return "Windows"

    def is_docker_installed(self) -> bool:
        return shutil.which("docker") is not None

    def install_docker_instructions(self) -> str:
        return (
            "Install Docker Desktop for Windows:\n\n"
            "Prerequisites (choose one):\n"
            "  • WSL 2 (recommended): Open PowerShell as Admin and run:\n"
            "      wsl --install\n"
            "    Then restart your PC.\n"
            "  • Hyper-V: enabled via Windows Features (Pro/Enterprise/Education only).\n\n"
            "Install Docker Desktop:\n"
            "  Option A (winget — easiest):\n"
            "    winget install -e --id Docker.DockerDesktop\n\n"
            "  Option B (Chocolatey):\n"
            "    choco install docker-desktop\n\n"
            "  Option C (manual download):\n"
            "    https://www.docker.com/products/docker-desktop\n\n"
            "After installation:\n"
            "  1. Launch Docker Desktop from the Start menu.\n"
            "  2. Wait for the whale icon in the system tray to become steady.\n"
            "  3. Re-run:  esplay setup"
        )

    def offer_docker_install(self) -> bool:
        """Attempt automated Docker Desktop install via winget or Chocolatey.

        Returns True on success, False if no supported package manager is found
        or the user declines.
        """
        import questionary  # noqa: PLC0415

        if _winget_available():
            tool, cmd = "winget", [
                "winget", "install", "-e", "--id", "Docker.DockerDesktop",
                "--accept-package-agreements", "--accept-source-agreements",
            ]
        elif _choco_available():
            tool, cmd = "Chocolatey", ["choco", "install", "docker-desktop", "-y"]
        else:
            return False

        confirmed = questionary.confirm(
            f"Docker Desktop is not installed. Install it via {tool}?",
            default=True,
        ).ask()
        if not confirmed:
            return False

        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            return False

        # Docker Desktop needs to be launched manually after install on Windows.
        # Attempt to start it.
        self._try_launch_docker_desktop()
        return self.is_docker_installed()

    def open_url(self, url: str) -> None:
        # os.startfile is Windows-only and opens the URL in the default browser.
        try:
            os.startfile(url)  # type: ignore[attr-defined]
        except AttributeError:
            webbrowser.open(url)

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _try_launch_docker_desktop() -> None:
        """Best-effort attempt to launch Docker Desktop after install."""
        common_paths = [
            r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Docker\Docker\Docker Desktop.exe"),
        ]
        for path in common_paths:
            if os.path.exists(path):
                try:
                    subprocess.Popen([path])
                except OSError:
                    pass
                return
