"""Unit tests for TeardownService."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from esplay.config import EsplayConfig
from esplay.services.teardown_service import TeardownService
from esplay.state import EsplayState, StateManager


@pytest.fixture()
def cfg(tmp_path: Path) -> EsplayConfig:
    cfg = EsplayConfig()
    object.__setattr__(cfg, "state_dir", tmp_path / ".esplay")
    return cfg


@pytest.fixture()
def mock_runtime() -> MagicMock:
    return MagicMock()


def test_destroy_removes_kibana_then_es(cfg, mock_runtime, tmp_path):
    """Kibana must be removed before Elasticsearch."""
    state = StateManager(cfg.state_file)
    svc = TeardownService(cfg, mock_runtime, state)
    svc.run()

    stop_calls = [c.args[0] for c in mock_runtime.stop.call_args_list]
    remove_calls = [c.args[0] for c in mock_runtime.remove.call_args_list]

    # Kibana should be stopped/removed first
    assert stop_calls.index(cfg.kibana_container_name) < stop_calls.index(cfg.es_container_name)


def test_destroy_clears_state(cfg, mock_runtime, tmp_path):
    state = StateManager(cfg.state_file)
    # Write some state first
    state.save(EsplayState(elastic_password="secret", es_container_id="abc"))
    assert state.is_setup()

    svc = TeardownService(cfg, mock_runtime, state)
    svc.run()

    assert not state.is_setup()


def test_destroy_without_purge_keeps_volume(cfg, mock_runtime, tmp_path):
    state = StateManager(cfg.state_file)
    svc = TeardownService(cfg, mock_runtime, state)
    svc.run(purge_volume=False)

    mock_runtime.remove_volume.assert_not_called()


def test_destroy_with_purge_removes_volume(cfg, mock_runtime, tmp_path):
    state = StateManager(cfg.state_file)
    svc = TeardownService(cfg, mock_runtime, state)
    svc.run(purge_volume=True)

    mock_runtime.remove_volume.assert_called_once_with(cfg.volume_name)


def test_destroy_is_idempotent(cfg, mock_runtime, tmp_path):
    """Calling destroy twice should not raise."""
    state = StateManager(cfg.state_file)
    svc = TeardownService(cfg, mock_runtime, state)
    svc.run()
    svc.run()  # Second call — should not raise
