"""TeardownService — orchestrates cluster destruction.

This is the Command object for `esplay destroy`.
"""

from __future__ import annotations

from esplay.config import EsplayConfig
from esplay.domain.cluster_manager import ClusterManager
from esplay.domain.kibana_manager import KibanaManager
from esplay.runtime.base import ContainerRuntime
from esplay.state import StateManager


class TeardownService:
    """Use-case service for `esplay destroy`."""

    def __init__(
        self,
        config: EsplayConfig,
        runtime: ContainerRuntime,
        state: StateManager,
    ) -> None:
        self._cfg = config
        self._runtime = runtime
        self._state = state

    def run(self, *, purge_volume: bool = False) -> None:
        """Tear down all esplay resources.

        Idempotent: safe to run even if resources don't exist.
        """
        cfg = self._cfg

        # Stop and remove Kibana first (depends on ES).
        kibana = KibanaManager(self._runtime, cfg)
        kibana.remove()

        # Stop and remove Elasticsearch.
        cluster = ClusterManager(self._runtime, cfg)
        cluster.remove()

        # Remove the shared network.
        self._runtime.remove_network(cfg.network_name)

        # Optionally remove the data volume.
        if purge_volume:
            self._runtime.remove_volume(cfg.volume_name)

        # Clear local state.
        self._state.clear()
