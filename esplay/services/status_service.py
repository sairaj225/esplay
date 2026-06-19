"""StatusService — gathers the current state of all esplay resources."""

from __future__ import annotations

from dataclasses import dataclass

import requests

from esplay.config import EsplayConfig
from esplay.domain.cluster_manager import ClusterManager
from esplay.domain.kibana_manager import KibanaManager
from esplay.runtime.base import ContainerRuntime
from esplay.state import EsplayState, StateManager


@dataclass
class PlaygroundStatus:
    """Snapshot of the full playground state."""

    es_running: bool
    es_container_status: str
    kibana_running: bool
    kibana_container_status: str
    kibana_available: bool
    cluster_health: str  # "green" | "yellow" | "red" | "unreachable"
    kibana_status: str   # "available" | "degraded" | "unreachable"
    doc_count: int
    es_url: str
    kibana_url: str
    state: EsplayState


class StatusService:
    """Use-case service for `esplay status`."""

    def __init__(
        self,
        config: EsplayConfig,
        runtime: ContainerRuntime,
        state: StateManager,
    ) -> None:
        self._cfg = config
        self._runtime = runtime
        self._state = state

    def run(self) -> PlaygroundStatus:
        cfg = self._cfg
        saved = self._state.load()

        cluster = ClusterManager(self._runtime, cfg)
        kibana = KibanaManager(self._runtime, cfg)

        es_cs = cluster.get_status()
        kb_cs = kibana.get_status()

        es_running = es_cs is not None and es_cs.running
        es_container_status = es_cs.status if es_cs else "not found"

        kibana_running = kb_cs is not None and kb_cs.running
        kibana_container_status = kb_cs.status if kb_cs else "not found"

        # Cluster health
        cluster_health = "unreachable"
        doc_count = 0
        if es_running and saved.elastic_password:
            health = cluster.cluster_health(saved.elastic_password)
            cluster_health = health.get("status", "unreachable")
            # doc count
            try:
                resp = requests.get(
                    f"{cfg.es_url}/users/_count",
                    auth=("elastic", saved.elastic_password),
                    timeout=5,
                )
                if resp.ok:
                    doc_count = resp.json().get("count", 0)
            except Exception:
                pass

        # Kibana status
        kibana_status = "disabled"
        kibana_available = False
        if cfg.with_kibana and kibana_running:
            kibana_status = kibana.kibana_status()
            kibana_available = kibana_status == "available"

        return PlaygroundStatus(
            es_running=es_running,
            es_container_status=es_container_status,
            kibana_running=kibana_running,
            kibana_container_status=kibana_container_status,
            kibana_available=kibana_available,
            cluster_health=cluster_health,
            kibana_status=kibana_status,
            doc_count=doc_count,
            es_url=cfg.es_url,
            kibana_url=cfg.kibana_url,
            state=saved,
        )
