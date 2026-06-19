"""RuntimeFactory — selects the ContainerRuntime implementation.

To add Podman or Colima:
  1. Implement ContainerRuntime in esplay/runtime/<engine>.py.
  2. Add it to _build_registry() below.
  3. No other files need changing.
"""

from __future__ import annotations

from esplay.runtime.base import ContainerRuntime


def _build_registry() -> dict[str, type[ContainerRuntime]]:
    from esplay.runtime.docker import DockerRuntime  # noqa: PLC0415

    return {
        "docker": DockerRuntime,
        # Future:
        # "podman": PodmanRuntime,
        # "colima": ColimaRuntime,
    }


class RuntimeFactory:
    """Returns a ContainerRuntime implementation.

    v1 defaults to Docker.  Pass ``runtime="podman"`` etc. to select another
    once additional implementations are registered.
    """

    @staticmethod
    def get(runtime: str = "docker") -> ContainerRuntime:
        registry = _build_registry()
        cls = registry.get(runtime)
        if cls is None:
            available = ", ".join(registry)
            raise ValueError(
                f"Unknown runtime {runtime!r}. Available: {available}."
            )
        return cls()
