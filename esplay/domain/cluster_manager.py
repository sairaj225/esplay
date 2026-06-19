"""ClusterManager — lifecycle management for the Elasticsearch container.

Depends only on ContainerRuntime (interface) — never on DockerRuntime directly.
This is an intentional design choice: swapping the runtime (Podman, Colima, …)
requires zero changes here.
"""

from __future__ import annotations

import time

import requests

from esplay.config import EsplayConfig
from esplay.errors import ClusterUnhealthyError
from esplay.runtime.base import ContainerConfig, ContainerRuntime, ContainerStatus


class ClusterManager:
    """Creates, monitors, and removes the Elasticsearch container."""

    def __init__(self, runtime: ContainerRuntime, config: EsplayConfig) -> None:
        self._runtime = runtime
        self._cfg = config

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self, elastic_password: str, network_id: str) -> str:  # noqa: ARG002
        """Start the Elasticsearch container and return its ID.

        NOTE: This is a LOCAL-LEARNING-ONLY setup.
          - HTTP (not HTTPS) is used to spare learners from TLS certificate setup.
          - xpack.security is ENABLED so learners practice real authentication.
          For production use, enable xpack.security.http.ssl and use HTTPS.
        """
        cfg = ContainerConfig(
            image=self._cfg.es_image,
            name=self._cfg.es_container_name,
            env={
                "discovery.type": "single-node",
                "xpack.security.enabled": "true",
                # HTTP only — local learning simplification (see docstring).
                "xpack.security.http.ssl.enabled": "false",
                "ELASTIC_PASSWORD": elastic_password,
                "ES_JAVA_OPTS": (
                    f"-Xms{self._cfg.es_heap_size} -Xmx{self._cfg.es_heap_size}"
                ),
            },
            ports={self._cfg.es_port: 9200},
            volumes={self._cfg.volume_name: "/usr/share/elasticsearch/data"},
            network=self._cfg.network_name,
            labels=self._cfg.container_label,
            ulimits=[
                {"name": "memlock", "soft": -1, "hard": -1},
                {"name": "nofile", "soft": 65536, "hard": 65536},
            ],
        )
        return self._runtime.start(cfg)

    def stop(self) -> None:
        self._runtime.stop(self._cfg.es_container_name)

    def remove(self) -> None:
        self._runtime.stop(self._cfg.es_container_name)
        self._runtime.remove(self._cfg.es_container_name, force=True)

    # ── Health ────────────────────────────────────────────────────────────────

    def wait_healthy(
        self,
        elastic_password: str,
        *,
        on_tick: "Callable[[int], None] | None" = None,
    ) -> None:
        """Block until the cluster is yellow or green, or raise ClusterUnhealthyError."""
        from typing import Callable  # noqa: PLC0415 (avoid top-level circular)

        deadline = time.time() + self._cfg.es_health_timeout
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            if on_tick:
                on_tick(attempt)
            try:
                resp = requests.get(
                    f"{self._cfg.es_url}/_cluster/health",
                    auth=("elastic", elastic_password),
                    timeout=5,
                )
                if resp.status_code == 200:
                    status = resp.json().get("status", "red")
                    if status in ("yellow", "green"):
                        return
            except requests.RequestException:
                pass
            time.sleep(self._cfg.health_poll_interval)

        raise ClusterUnhealthyError(self._cfg.es_health_timeout)

    def cluster_health(self, elastic_password: str) -> dict:
        """Return the cluster health JSON, or an empty dict if unreachable."""
        try:
            resp = requests.get(
                f"{self._cfg.es_url}/_cluster/health",
                auth=("elastic", elastic_password),
                timeout=5,
            )
            if resp.ok:
                return resp.json()
        except requests.RequestException:
            pass
        return {}

    def is_running(self) -> bool:
        status = self._runtime.get_status(self._cfg.es_container_name)
        return status is not None and status.running

    def get_status(self) -> ContainerStatus | None:
        return self._runtime.get_status(self._cfg.es_container_name)

    # ── kibana_system password ────────────────────────────────────────────────

    def set_kibana_system_password(
        self, elastic_password: str, kibana_password: str
    ) -> None:
        """Set the built-in kibana_system user password via the ES security API."""
        url = f"{self._cfg.es_url}/_security/user/kibana_system/_password"
        resp = requests.post(
            url,
            json={"password": kibana_password},
            auth=("elastic", elastic_password),
            timeout=10,
        )
        resp.raise_for_status()
