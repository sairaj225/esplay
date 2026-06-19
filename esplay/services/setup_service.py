"""SetupService — orchestrates end-to-end cluster provisioning.

This is the Command object for `esplay setup`.  It coordinates the
platform, runtime, domain services, and state — without knowing about
any concrete implementation.
"""

from __future__ import annotations

from typing import Callable

from elasticsearch import Elasticsearch

from esplay.config import EsplayConfig
from esplay.datasets.registry import get_dataset
from esplay.domain.cluster_manager import ClusterManager
from esplay.domain.credentials import generate_password
from esplay.domain.data_seeder import DataSeeder
from esplay.domain.index_provisioner import IndexProvisioner
from esplay.domain.kibana_manager import KibanaManager
from esplay.errors import DaemonNotRunningError, DockerNotFoundError, EsplayError
from esplay.platform.base import PlatformProvider
from esplay.runtime.base import ContainerRuntime
from esplay.state import EsplayState, StateManager


class SetupProgress:
    """Simple event bus for setup progress — injected into SetupService."""

    def step(self, message: str) -> None: ...
    def success(self, message: str) -> None: ...
    def warning(self, message: str) -> None: ...
    def spinner_start(self, message: str) -> None: ...
    def spinner_stop(self, success: bool = True, message: str = "") -> None: ...
    def progress(self, done: int, total: int) -> None: ...


class SetupService:
    """Use-case service for `esplay setup`."""

    def __init__(
        self,
        config: EsplayConfig,
        platform: PlatformProvider,
        runtime: ContainerRuntime,
        state: StateManager,
        progress: SetupProgress,
    ) -> None:
        self._cfg = config
        self._platform = platform
        self._runtime = runtime
        self._state = state
        self._progress = progress

    def run(self) -> EsplayState:
        """Execute the full setup sequence.  Returns the final state."""
        cfg = self._cfg
        p = self._progress

        # ── Step 1: Preflight ─────────────────────────────────────────────────
        p.step("[1/9] Preflight checks")
        self._preflight()

        # ── Step 2: Pull images ───────────────────────────────────────────────
        p.step("[2/9] Pulling images (this may take a few minutes on first run)")
        self._pull_images()

        # ── Step 3: Generate credentials ──────────────────────────────────────
        p.step("[3/9] Generating credentials")
        existing_state = self._state.load()

        # Idempotent: reuse existing passwords so `setup` can be re-run.
        elastic_password = existing_state.elastic_password or generate_password()
        kibana_password = existing_state.kibana_system_password or generate_password()

        # ── Step 4: Create network ────────────────────────────────────────────
        p.step("[4/9] Creating Docker network")
        network_id = self._runtime.create_network(cfg.network_name)

        # ── Step 5: Start Elasticsearch ───────────────────────────────────────
        cluster = ClusterManager(self._runtime, cfg)

        if cluster.is_running():
            p.warning("Elasticsearch container already running — skipping start")
            es_container_id = (existing_state.es_container_id or "")
        else:
            p.step("[5/9] Starting Elasticsearch")
            es_container_id = cluster.start(elastic_password, network_id)

        # ── Step 6: Wait for ES health ────────────────────────────────────────
        p.step("[6/9] Waiting for Elasticsearch to become healthy …")
        cluster.wait_healthy(elastic_password)
        p.success("Elasticsearch is healthy")

        # Build ES client.
        es = Elasticsearch(
            cfg.es_url,
            basic_auth=("elastic", elastic_password),
            verify_certs=False,
            ssl_show_warn=False,
        )

        # ── Step 7: Kibana ────────────────────────────────────────────────────
        kibana_id = ""
        kibana_mgr = KibanaManager(self._runtime, cfg)
        if cfg.with_kibana:
            # Set kibana_system password before starting Kibana.
            p.step("[7/9] Configuring Kibana credentials")
            cluster.set_kibana_system_password(elastic_password, kibana_password)

            if kibana_mgr.is_running():
                p.warning("Kibana container already running — skipping start")
                kibana_id = existing_state.kibana_container_id or ""
            else:
                p.step("[7/9] Starting Kibana")
                kibana_id = kibana_mgr.start(kibana_password)

            p.step("[7/9] Waiting for Kibana to become available (this can take ~60 s) …")
            kibana_mgr.wait_available()
            p.success("Kibana is available")
        else:
            p.warning("Kibana skipped (--no-kibana)")

        # ── Step 8: Provision index ───────────────────────────────────────────
        p.step("[8/9] Provisioning index")
        dataset = get_dataset(cfg.dataset)
        provisioner = IndexProvisioner(es)
        created = provisioner.ensure_index(dataset)
        if not created:
            p.warning(f"Index '{dataset.index_name()}' already exists — skipping creation")

        # ── Step 9: Seed data ─────────────────────────────────────────────────
        seeder = DataSeeder(es)
        if seeder.is_seeded(dataset):
            p.warning(f"Index '{dataset.index_name()}' already has data — skipping seeding")
            doc_count = provisioner.doc_count(dataset.index_name())
        else:
            p.step("[9/9] Seeding data …")
            doc_count = seeder.seed(
                dataset,
                on_progress=lambda done, total: p.progress(done, total),
            )
            p.success(f"Seeded {doc_count} documents into '{dataset.index_name()}'")

        # ── Persist state ─────────────────────────────────────────────────────
        final_state = EsplayState(
            elastic_password=elastic_password,
            kibana_system_password=kibana_password,
            es_container_id=es_container_id,
            kibana_container_id=kibana_id,
            network_id=network_id,
            stack_version=cfg.stack_version,
            es_port=cfg.es_port,
            kibana_port=cfg.kibana_port,
            with_kibana=cfg.with_kibana,
            doc_count=doc_count,
        )
        self._state.save(final_state)
        return final_state

    # ── Private helpers ───────────────────────────────────────────────────────

    def _preflight(self) -> None:
        if not self._platform.is_docker_installed():
            installed = self._platform.offer_docker_install()
            if not installed:
                raise DockerNotFoundError()

        if not self._runtime.is_daemon_running():
            raise DaemonNotRunningError()

    def _pull_images(self) -> None:
        self._runtime.pull_image(self._cfg.es_image)
        if self._cfg.with_kibana:
            self._runtime.pull_image(self._cfg.kibana_image)
