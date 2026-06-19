"""KibanaManager — lifecycle management for the Kibana container.

Depends only on ContainerRuntime — no Kibana-specific code leaks into the
runtime layer.  Kibana is "just another container" from the runtime's perspective.
"""

from __future__ import annotations

import time

import requests

from esplay.config import EsplayConfig
from esplay.errors import KibanaUnhealthyError
from esplay.runtime.base import ContainerConfig, ContainerRuntime, ContainerStatus


class KibanaManager:
    """Creates, monitors, and removes the Kibana container."""

    def __init__(self, runtime: ContainerRuntime, config: EsplayConfig) -> None:
        self._runtime = runtime
        self._cfg = config

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self, kibana_system_password: str) -> str:
        """Start the Kibana container and return its ID.

        Kibana connects to Elasticsearch using the kibana_system built-in user
        (not the elastic superuser — a best-practice even for local learning).
        It reaches ES over the shared Docker network by container name, because
        'localhost' inside the Kibana container refers to Kibana itself, not ES.
        """
        cfg = ContainerConfig(
            image=self._cfg.kibana_image,
            name=self._cfg.kibana_container_name,
            env={
                "ELASTICSEARCH_HOSTS": (
                    f"http://{self._cfg.es_container_name}:9200"
                ),
                "ELASTICSEARCH_USERNAME": "kibana_system",
                "ELASTICSEARCH_PASSWORD": kibana_system_password,
                "SERVER_HOST": "0.0.0.0",
                # Disable telemetry for a cleaner first-run experience.
                "TELEMETRY_ENABLED": "false",
                "XPACK_ENCRYPTEDSAMLOBJECTS_ENCRYPTIONKEY": "changeme-32-char-key-for-esplay!",
                "XPACK_SECURITY_ENCRYPTIONKEY": "changeme-32-char-key-for-esplay!",
                "XPACK_REPORTING_ENCRYPTIONKEY": "changeme-32-char-key-for-esplay!",
            },
            ports={self._cfg.kibana_port: 5601},
            network=self._cfg.network_name,
            labels=self._cfg.container_label,
        )
        return self._runtime.start(cfg)

    def stop(self) -> None:
        self._runtime.stop(self._cfg.kibana_container_name)

    def remove(self) -> None:
        self._runtime.stop(self._cfg.kibana_container_name)
        self._runtime.remove(self._cfg.kibana_container_name, force=True)

    # ── Health ────────────────────────────────────────────────────────────────

    def wait_available(
        self,
        *,
        on_tick: "Callable[[int], None] | None" = None,
    ) -> None:
        """Block until Kibana reports overall status 'available'."""
        from typing import Callable  # noqa: PLC0415

        deadline = time.time() + self._cfg.kibana_health_timeout
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            if on_tick:
                on_tick(attempt)
            try:
                resp = requests.get(
                    f"{self._cfg.kibana_url}/api/status",
                    timeout=5,
                    headers={"kbn-xsrf": "true"},
                )
                if resp.status_code == 200:
                    state = (
                        resp.json()
                        .get("status", {})
                        .get("overall", {})
                        .get("level", "")
                    )
                    if state == "available":
                        return
            except requests.RequestException:
                pass
            time.sleep(self._cfg.health_poll_interval)

        raise KibanaUnhealthyError(self._cfg.kibana_health_timeout)

    def kibana_status(self) -> str:
        """Return Kibana overall status level string, or 'unreachable'."""
        try:
            resp = requests.get(
                f"{self._cfg.kibana_url}/api/status",
                timeout=5,
                headers={"kbn-xsrf": "true"},
            )
            if resp.ok:
                return (
                    resp.json()
                    .get("status", {})
                    .get("overall", {})
                    .get("level", "unknown")
                )
        except requests.RequestException:
            pass
        return "unreachable"

    def is_running(self) -> bool:
        status = self._runtime.get_status(self._cfg.kibana_container_name)
        return status is not None and status.running

    def get_status(self) -> ContainerStatus | None:
        return self._runtime.get_status(self._cfg.kibana_container_name)
