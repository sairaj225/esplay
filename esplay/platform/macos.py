"""macOS PlatformProvider implementation."""

from __future__ import annotations

import shutil
import subprocess
import webbrowser

from esplay.platform.base import PlatformProvider


class MacOSPlatform(PlatformProvider):
    """macOS-specific platform operations."""

    def name(self) -> str:
        return "macOS"

    def is_docker_installed(self) -> bool:
        return shutil.which("docker") is not None

    def install_docker_instructions(self) -> str:
        return (
            "Install Docker Desktop for Mac:\n"
            "  Option A (Homebrew):  brew install --cask docker\n"
            "  Option B (manual):    https://www.docker.com/products/docker-desktop\n\n"
            "After installation, open Docker Desktop and wait for the whale icon\n"
            "in the menu bar to become steady, then re-run:  esplay setup"
        )

    def offer_docker_install(self) -> bool:
        """Try to install Docker Desktop via Homebrew.

        Returns True on success, False if Homebrew is missing or user declines.
        """
        if shutil.which("brew") is None:
            return False

        import questionary  # local import to avoid hard dep at module level

        confirmed = questionary.confirm(
            "Docker is not installed. Install Docker Desktop via Homebrew?",
            default=True,
        ).ask()

        if not confirmed:
            return False

        result = subprocess.run(
            ["brew", "install", "--cask", "docker"],
            check=False,
        )
        return result.returncode == 0

    def open_url(self, url: str) -> None:
        webbrowser.open(url)
