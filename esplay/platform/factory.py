"""PlatformFactory — selects the correct PlatformProvider at runtime.

To add a new OS:
  1. Implement PlatformProvider in a new module under esplay/platform/.
  2. Add one entry to _build_registry() below — that's it.
  3. No other files need changing.
"""

from __future__ import annotations

import platform

from esplay.errors import UnsupportedPlatformError
from esplay.platform.base import PlatformProvider


def _build_registry() -> dict[str, type[PlatformProvider]]:
    """Late-import registry so unused platforms don't cause import errors on
    OSes where a given module's dependencies aren't available."""
    from esplay.platform.linux import LinuxPlatform    # noqa: PLC0415
    from esplay.platform.macos import MacOSPlatform   # noqa: PLC0415
    from esplay.platform.windows import WindowsPlatform  # noqa: PLC0415

    return {
        "Darwin":  MacOSPlatform,
        "Linux":   LinuxPlatform,
        "Windows": WindowsPlatform,
    }


class PlatformFactory:
    """Returns the appropriate PlatformProvider for the current OS."""

    @staticmethod
    def get() -> PlatformProvider:
        system = platform.system()
        registry = _build_registry()
        cls = registry.get(system)
        if cls is None:
            raise UnsupportedPlatformError(system)
        return cls()
