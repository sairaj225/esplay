"""Unit tests for DockerRuntime.

Uses pytest-mock to avoid requiring a live Docker daemon.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from esplay.errors import (
    ContainerStartError,
    DaemonNotRunningError,
    DockerNotFoundError,
    ImagePullError,
)
from esplay.runtime.docker import DockerRuntime


@pytest.fixture()
def rt() -> DockerRuntime:
    return DockerRuntime()


# ── is_installed / is_daemon_running ─────────────────────────────────────────

def test_is_installed_returns_true_when_docker_on_path(rt):
    with patch("esplay.runtime.docker.shutil.which", return_value="/usr/bin/docker"):
        assert rt.is_installed() is True


def test_is_installed_returns_false_when_not_on_path(rt):
    with patch("esplay.runtime.docker.shutil.which", return_value=None):
        assert rt.is_installed() is False


def test_is_daemon_running_returns_false_on_exception(rt):
    with patch("esplay.runtime.docker.docker.from_env", side_effect=Exception("no socket")):
        assert rt.is_daemon_running() is False


# ── pull_image ────────────────────────────────────────────────────────────────

def test_pull_image_raises_on_api_error(rt):
    import docker.errors as de

    mock_client = MagicMock()
    mock_client.images.pull.side_effect = de.APIError("pull failed")
    rt._client = mock_client

    with pytest.raises(ImagePullError):
        rt.pull_image("docker.elastic.co/elasticsearch/elasticsearch:8.13.4")


# ── start ─────────────────────────────────────────────────────────────────────

def test_start_raises_on_api_error(rt):
    import docker.errors as de
    from esplay.runtime.base import ContainerConfig

    mock_client = MagicMock()
    mock_client.containers.run.side_effect = de.APIError("conflict")
    rt._client = mock_client

    cfg = ContainerConfig(image="someimage", name="test-container")
    with pytest.raises(ContainerStartError):
        rt.start(cfg)


# ── get_status ────────────────────────────────────────────────────────────────

def test_get_status_returns_none_when_not_found(rt):
    import docker.errors as de

    mock_client = MagicMock()
    mock_client.containers.get.side_effect = de.NotFound("nope")
    rt._client = mock_client

    assert rt.get_status("ghost-container") is None


def test_get_status_returns_status_when_running(rt):
    mock_container = MagicMock()
    mock_container.id = "abc123"
    mock_container.name = "esplay-elasticsearch"
    mock_container.status = "running"
    mock_container.image.tags = ["docker.elastic.co/elasticsearch/elasticsearch:8.13.4"]

    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_container
    rt._client = mock_client

    status = rt.get_status("esplay-elasticsearch")
    assert status is not None
    assert status.running is True
    assert status.name == "esplay-elasticsearch"


# ── network ───────────────────────────────────────────────────────────────────

def test_create_network_returns_existing_id(rt):
    existing_net = MagicMock()
    existing_net.id = "existing-net-id"

    mock_client = MagicMock()
    mock_client.networks.list.return_value = [existing_net]
    rt._client = mock_client

    net_id = rt.create_network("esplay-net")
    assert net_id == "existing-net-id"
    mock_client.networks.create.assert_not_called()


def test_remove_network_is_idempotent(rt):
    mock_client = MagicMock()
    mock_client.networks.list.return_value = []
    rt._client = mock_client

    # Should not raise even if network doesn't exist.
    rt.remove_network("esplay-net")
