"""DockerRuntime — ContainerRuntime backed by the Docker SDK.

NOTE: This is a LOCAL-LEARNING-ONLY setup.
  - TLS is disabled on Elasticsearch (HTTP only).
  - Security is still enabled (authentication required) for educational realism.
  - NEVER use this configuration for a production or publicly accessible deployment.
"""

from __future__ import annotations

import shutil
from typing import Iterator

import docker
import docker.errors
from docker.types import Ulimit

from esplay.errors import (
    ContainerStartError,
    DaemonNotRunningError,
    DockerNotFoundError,
    ImagePullError,
    NetworkError,
)
from esplay.runtime.base import ContainerConfig, ContainerRuntime, ContainerStatus


class DockerRuntime(ContainerRuntime):
    """ContainerRuntime implementation using the Docker Python SDK."""

    def __init__(self) -> None:
        self._client: docker.DockerClient | None = None

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _get_client(self) -> docker.DockerClient:
        if self._client is None:
            try:
                self._client = docker.from_env()
            except docker.errors.DockerException as exc:
                if not self.is_installed():
                    raise DockerNotFoundError() from exc
                raise DaemonNotRunningError() from exc
        return self._client

    # ── ContainerRuntime interface ────────────────────────────────────────────

    def is_installed(self) -> bool:
        return shutil.which("docker") is not None

    def is_daemon_running(self) -> bool:
        try:
            client = docker.from_env()
            client.ping()
            return True
        except Exception:
            return False

    def pull_image(self, image: str) -> None:
        """Pull *image*, printing progress dots (Rich spinners handle the UI layer)."""
        client = self._get_client()
        try:
            client.images.pull(image)
        except docker.errors.APIError as exc:
            raise ImagePullError(
                f"Failed to pull image {image!r}: {exc}",
                hint="Check your internet connection and that the image tag is correct.",
            ) from exc

    def start(self, config: ContainerConfig) -> str:
        client = self._get_client()

        ports: dict = {}
        for host_port, container_port in config.ports.items():
            ports[f"{container_port}/tcp"] = host_port

        volumes: dict = {}
        for src, dst in config.volumes.items():
            volumes[src] = {"bind": dst, "mode": "rw"}

        ulimits = [
            Ulimit(name=u["name"], soft=u.get("soft"), hard=u.get("hard"))
            for u in config.ulimits
        ]

        try:
            container = client.containers.run(
                image=config.image,
                name=config.name,
                detach=True,
                environment=config.env,
                ports=ports,
                volumes=volumes,
                network=config.network,
                labels=config.labels,
                ulimits=ulimits or None,
                mem_limit=config.mem_limit,
                remove=False,
            )
            return container.id  # type: ignore[union-attr]
        except docker.errors.APIError as exc:
            raise ContainerStartError(
                f"Failed to start container {config.name!r}: {exc}",
                hint="Check `docker ps -a` for conflicts and try `esplay destroy` first.",
            ) from exc

    def stop(self, name: str) -> None:
        client = self._get_client()
        try:
            container = client.containers.get(name)
            container.stop(timeout=15)
        except docker.errors.NotFound:
            pass  # idempotent
        except docker.errors.APIError:
            pass

    def remove(self, name: str, *, force: bool = False) -> None:
        client = self._get_client()
        try:
            container = client.containers.get(name)
            container.remove(force=force)
        except docker.errors.NotFound:
            pass  # idempotent

    def get_status(self, name: str) -> ContainerStatus | None:
        client = self._get_client()
        try:
            container = client.containers.get(name)
            container.reload()
            return ContainerStatus(
                id=container.id,  # type: ignore[arg-type]
                name=container.name,  # type: ignore[arg-type]
                running=container.status == "running",
                status=container.status,  # type: ignore[arg-type]
                image=container.image.tags[0] if container.image.tags else "",  # type: ignore[union-attr]
            )
        except docker.errors.NotFound:
            return None

    def logs(self, name: str, *, follow: bool = False, tail: int = 100) -> Iterator[str]:
        client = self._get_client()
        try:
            container = client.containers.get(name)
            for chunk in container.logs(stream=True, follow=follow, tail=tail):
                line = chunk.decode("utf-8", errors="replace").rstrip("\n")
                if line:
                    yield line
        except docker.errors.NotFound:
            yield f"[container {name!r} not found]"

    def create_network(self, name: str) -> str:
        client = self._get_client()
        try:
            # Return existing network if it already exists (idempotent).
            existing = client.networks.list(names=[name])
            if existing:
                return existing[0].id  # type: ignore[index,union-attr]
            network = client.networks.create(name, driver="bridge")
            return network.id  # type: ignore[union-attr]
        except docker.errors.APIError as exc:
            raise NetworkError(
                f"Failed to create network {name!r}: {exc}",
            ) from exc

    def remove_network(self, name: str) -> None:
        client = self._get_client()
        try:
            networks = client.networks.list(names=[name])
            for net in networks:
                net.remove()
        except docker.errors.APIError:
            pass  # idempotent

    def remove_volume(self, name: str) -> None:
        client = self._get_client()
        try:
            volume = client.volumes.get(name)
            volume.remove(force=True)
        except docker.errors.NotFound:
            pass  # idempotent

    def volume_exists(self, name: str) -> bool:
        client = self._get_client()
        try:
            client.volumes.get(name)
            return True
        except docker.errors.NotFound:
            return False
