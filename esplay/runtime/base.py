"""ContainerRuntime — extension seam for container engine abstraction.

To add Podman, Colima, or any other runtime:
  1. Create esplay/runtime/<engine>.py implementing ContainerRuntime.
  2. Register it in esplay/runtime/factory.py.
  3. ClusterManager and KibanaManager will work unchanged because they depend
     only on this interface, never on DockerRuntime directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class ContainerConfig:
    """Declarative spec for a container run — a Builder-style value object."""

    image: str
    name: str
    env: dict[str, str] = field(default_factory=dict)
    ports: dict[int, int] = field(default_factory=dict)   # host_port → container_port
    volumes: dict[str, str] = field(default_factory=dict) # volume_name/host_path → container_path
    network: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    ulimits: list[dict] = field(default_factory=list)
    mem_limit: str | None = None


@dataclass
class ContainerStatus:
    """Snapshot of a container's current state."""

    id: str
    name: str
    running: bool
    status: str   # e.g. "running", "exited", "created"
    image: str


class ContainerRuntime(ABC):
    """Interface for a container engine.

    This is an intentional extension seam.  High-level services (ClusterManager,
    KibanaManager) receive this interface via dependency injection and must not
    reference DockerRuntime (or any concrete implementation) directly.
    """

    @abstractmethod
    def is_installed(self) -> bool:
        """Return True if the runtime binary is on PATH."""

    @abstractmethod
    def is_daemon_running(self) -> bool:
        """Return True if the daemon/socket is reachable."""

    @abstractmethod
    def pull_image(self, image: str) -> None:
        """Pull *image* from a registry, streaming progress to the terminal."""

    @abstractmethod
    def start(self, config: ContainerConfig) -> str:
        """Create and start a container.  Returns the container ID."""

    @abstractmethod
    def stop(self, name: str) -> None:
        """Stop a running container (no-op if not running)."""

    @abstractmethod
    def remove(self, name: str, *, force: bool = False) -> None:
        """Remove a container (no-op if it doesn't exist)."""

    @abstractmethod
    def get_status(self, name: str) -> ContainerStatus | None:
        """Return status for *name*, or None if the container does not exist."""

    @abstractmethod
    def logs(self, name: str, *, follow: bool = False, tail: int = 100) -> Iterator[str]:
        """Yield log lines for *name*."""

    @abstractmethod
    def create_network(self, name: str) -> str:
        """Create a user-defined bridge network.  Returns the network ID.
        No-op (returns existing ID) if the network already exists."""

    @abstractmethod
    def remove_network(self, name: str) -> None:
        """Remove a network (no-op if it doesn't exist)."""

    @abstractmethod
    def remove_volume(self, name: str) -> None:
        """Remove a named volume (no-op if it doesn't exist)."""

    @abstractmethod
    def volume_exists(self, name: str) -> bool:
        """Return True if a named volume exists."""
