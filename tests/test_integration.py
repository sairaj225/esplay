"""Integration tests — require a live Docker daemon.

Run with:
  pytest -m integration tests/test_integration.py

These tests actually spin up Docker containers and make real HTTP calls.
They are skipped by default (CI can opt in via the marker).

NOTE: These tests take several minutes on first run due to image pulling.
"""

from __future__ import annotations

import time

import pytest
import requests

from esplay.config import EsplayConfig
from esplay.domain.cluster_manager import ClusterManager
from esplay.domain.credentials import generate_password
from esplay.domain.kibana_manager import KibanaManager
from esplay.runtime.docker import DockerRuntime
from esplay.state import StateManager


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def runtime() -> DockerRuntime:
    rt = DockerRuntime()
    if not rt.is_daemon_running():
        pytest.skip("Docker daemon is not running")
    return rt


@pytest.fixture(scope="module")
def cfg(tmp_path_factory) -> EsplayConfig:
    tmp_path = tmp_path_factory.mktemp("esplay-integration")
    cfg = EsplayConfig()
    object.__setattr__(cfg, "state_dir", tmp_path / ".esplay")
    object.__setattr__(cfg, "with_kibana", False)  # skip Kibana for speed
    object.__setattr__(cfg, "es_container_name", "esplay-integration-test")
    object.__setattr__(cfg, "network_name", "esplay-integration-net")
    object.__setattr__(cfg, "volume_name", "esplay-integration-data")
    object.__setattr__(cfg, "es_port", 19200)  # avoid conflicts
    return cfg


@pytest.fixture(scope="module", autouse=True)
def cluster(runtime, cfg):
    """Start a real ES cluster, yield, then tear it down."""
    password = generate_password()
    network_id = runtime.create_network(cfg.network_name)
    cluster = ClusterManager(runtime, cfg)

    container_id = cluster.start(password, network_id)
    cluster.wait_healthy(password)

    yield cluster, password

    # Teardown
    cluster.remove()
    runtime.remove_network(cfg.network_name)
    runtime.remove_volume(cfg.volume_name)


def test_cluster_is_running(cluster, runtime, cfg):
    _, _ = cluster
    status = runtime.get_status(cfg.es_container_name)
    assert status is not None
    assert status.running is True


def test_cluster_health_is_yellow_or_green(cluster, cfg):
    mgr, password = cluster
    health = mgr.cluster_health(password)
    assert health.get("status") in ("yellow", "green")


def test_can_create_and_search_index(cluster, cfg):
    mgr, password = cluster
    from elasticsearch import Elasticsearch
    from esplay.datasets.users import UsersDataset
    from esplay.domain.data_seeder import DataSeeder
    from esplay.domain.index_provisioner import IndexProvisioner

    es = Elasticsearch(
        f"http://localhost:{cfg.es_port}",
        basic_auth=("elastic", password),
        verify_certs=False,
    )
    dataset = UsersDataset()
    provisioner = IndexProvisioner(es)
    provisioner.ensure_index(dataset)

    seeder = DataSeeder(es)
    count = seeder.seed(dataset)
    assert count >= 50

    # Give ES a moment to refresh
    time.sleep(1)
    result = es.search(index="users", query={"match_all": {}}, size=1)
    assert result["hits"]["total"]["value"] >= 50
