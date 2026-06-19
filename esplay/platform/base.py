"""PlatformProvider — extension seam for OS-specific behaviour.

To add a new OS (e.g. Linux, Windows):
  1. Create esplay/platform/<os>.py implementing PlatformProvider.
  2. Register it in esplay/platform/factory.py.
  3. No other files need to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class PlatformProvider(ABC):
    """Interface for OS-specific operations.

    This is an intentional extension seam.  All platform-dependent logic
    must live in a concrete subclass — never inline in services.
    """

    @abstractmethod
    def name(self) -> str:
        """Human-readable OS name (e.g. 'macOS')."""

    @abstractmethod
    def is_docker_installed(self) -> bool:
        """Return True if the Docker CLI / runtime binary is on PATH."""

    @abstractmethod
    def install_docker_instructions(self) -> str:
        """Return step-by-step instructions (multi-line string) for installing Docker."""

    @abstractmethod
    def offer_docker_install(self) -> bool:
        """Attempt an automated Docker install.

        Returns True if the install succeeded, False if the user declined or
        it failed.  Raise DockerNotFoundError if install fails fatally.
        """

    @abstractmethod
    def open_url(self, url: str) -> None:
        """Open *url* in the system default browser."""
