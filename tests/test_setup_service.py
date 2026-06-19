"""Unit tests for SetupService.

All external dependencies (runtime, platform, ES) are mocked so these tests
run without Docker or a live Elasticsearch cluster.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from esplay.config import EsplayConfig
from esplay.errors import DaemonNotRunningError, DockerNotFoundError
from esplay.runtime.base import ContainerStatus
from esplay.services.setup_service import SetupProgress, SetupService
from esplay.state import EsplayState, StateManager


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def cfg(tmp_path: Path) -> EsplayConfig:
    cfg = EsplayConfig()
    object.__setattr__(cfg, "state_dir", tmp_path / ".esplay")
    object.__setattr__(cfg, "with_kibana", False)  # faster unit tests
    object.__setattr__(cfg, "es_health_timeout", 5)
    return cfg


@pytest.fixture()
def mock_runtime() -> MagicMock:
    rt = MagicMock()
    rt.is_installed.return_value = True
    rt.is_daemon_running.return_value = True
    rt.pull_image.return_value = None
    rt.create_network.return_value = "net-id-123"
    rt.start.return_value = "container-id-abc"
    rt.get_status.return_value = ContainerStatus(
        id="container-id-abc",
        name="esplay-elasticsearch",
        running=True,
        status="running",
        image="docker.elastic.co/elasticsearch/elasticsearch:8.13.4",
    )
    return rt


@pytest.fixture()
def mock_platform() -> MagicMock:
    p = MagicMock()
    p.is_docker_installed.return_value = True
    return p


@pytest.fixture()
def silent_progress() -> SetupProgress:
    """A SetupProgress that does nothing (suppresses all output in tests)."""
    return SetupProgress()


def _make_service(cfg, runtime, platform, tmp_path, progress) -> SetupService:
    state = StateManager(cfg.state_file)
    return SetupService(cfg, platform, runtime, state, progress)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_preflight_raises_when_docker_not_installed(cfg, mock_runtime, mock_platform, tmp_path, silent_progress):
    mock_platform.is_docker_installed.return_value = False
    mock_platform.offer_docker_install.return_value = False

    svc = _make_service(cfg, mock_runtime, mock_platform, tmp_path, silent_progress)
    with pytest.raises(DockerNotFoundError):
        svc._preflight()


def test_preflight_raises_when_daemon_not_running(cfg, mock_runtime, mock_platform, tmp_path, silent_progress):
    mock_runtime.is_daemon_running.return_value = False

    svc = _make_service(cfg, mock_runtime, mock_platform, tmp_path, silent_progress)
    with pytest.raises(DaemonNotRunningError):
        svc._preflight()


def test_setup_pulls_es_image_only_when_no_kibana(cfg, mock_runtime, mock_platform, tmp_path, silent_progress):
    """With --no-kibana, only the ES image should be pulled."""
    object.__setattr__(cfg, "with_kibana", False)

    svc = _make_service(cfg, mock_runtime, mock_platform, tmp_path, silent_progress)
    svc._preflight()
    svc._pull_images()

    pulled_images = [call.args[0] for call in mock_runtime.pull_image.call_args_list]
    assert any("elasticsearch" in img for img in pulled_images)
    assert not any("kibana" in img for img in pulled_images)


def test_setup_pulls_kibana_image_when_with_kibana(cfg, mock_runtime, mock_platform, tmp_path, silent_progress):
    object.__setattr__(cfg, "with_kibana", True)

    svc = _make_service(cfg, mock_runtime, mock_platform, tmp_path, silent_progress)
    svc._pull_images()

    pulled_images = [call.args[0] for call in mock_runtime.pull_image.call_args_list]
    assert any("kibana" in img for img in pulled_images)


@patch("esplay.services.setup_service.ClusterManager")
@patch("esplay.services.setup_service.IndexProvisioner")
@patch("esplay.services.setup_service.DataSeeder")
@patch("esplay.services.setup_service.Elasticsearch")
def test_setup_saves_state(
    mock_es_cls, mock_seeder_cls, mock_provisioner_cls, mock_cluster_cls,
    cfg, mock_runtime, mock_platform, tmp_path, silent_progress,
):
    """SetupService.run() should persist state to disk."""
    # Configure mocks
    mock_cluster = mock_cluster_cls.return_value
    mock_cluster.is_running.return_value = False
    mock_cluster.start.return_value = "es-container-123"
    mock_cluster.wait_healthy.return_value = None
    mock_cluster.cluster_health.return_value = {"status": "green"}

    mock_provisioner = mock_provisioner_cls.return_value
    mock_provisioner.ensure_index.return_value = True
    mock_provisioner.doc_count.return_value = 87

    mock_seeder = mock_seeder_cls.return_value
    mock_seeder.is_seeded.return_value = False
    mock_seeder.seed.return_value = 87

    state_mgr = StateManager(cfg.state_file)
    svc = SetupService(cfg, mock_platform, mock_runtime, state_mgr, silent_progress)
    result = svc.run()

    assert result.elastic_password != ""
    assert result.es_container_id == "es-container-123"
    assert result.doc_count == 87

    # State file should exist and be readable.
    saved = state_mgr.load()
    assert saved.elastic_password == result.elastic_password


@patch("esplay.services.setup_service.ClusterManager")
@patch("esplay.services.setup_service.IndexProvisioner")
@patch("esplay.services.setup_service.DataSeeder")
@patch("esplay.services.setup_service.Elasticsearch")
def test_setup_is_idempotent_when_already_seeded(
    mock_es_cls, mock_seeder_cls, mock_provisioner_cls, mock_cluster_cls,
    cfg, mock_runtime, mock_platform, tmp_path, silent_progress,
):
    """Re-running setup when data exists should not re-seed."""
    mock_cluster = mock_cluster_cls.return_value
    mock_cluster.is_running.return_value = True  # already running
    mock_cluster.wait_healthy.return_value = None

    mock_provisioner = mock_provisioner_cls.return_value
    mock_provisioner.ensure_index.return_value = False  # already exists
    mock_provisioner.doc_count.return_value = 87

    mock_seeder = mock_seeder_cls.return_value
    mock_seeder.is_seeded.return_value = True  # already seeded

    state_mgr = StateManager(cfg.state_file)
    svc = SetupService(cfg, mock_platform, mock_runtime, state_mgr, silent_progress)
    svc.run()

    mock_seeder.seed.assert_not_called()
