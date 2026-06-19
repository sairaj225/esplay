"""Unit tests for DataSeeder and IndexProvisioner."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from esplay.datasets.users import UsersDataset
from esplay.domain.data_seeder import DataSeeder
from esplay.domain.index_provisioner import IndexProvisioner
from esplay.errors import SeedError


@pytest.fixture()
def mock_es() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def dataset() -> UsersDataset:
    return UsersDataset()


# ── UsersDataset ──────────────────────────────────────────────────────────────

def test_users_dataset_index_name(dataset):
    assert dataset.index_name() == "users"


def test_users_dataset_documents_loaded(dataset):
    docs = dataset.documents()
    assert len(docs) >= 50, "Should have at least 50 seed documents"
    # Spot-check structure
    assert "first_name" in docs[0]
    assert "email" in docs[0]
    assert "salary" in docs[0]


def test_users_dataset_mapping_has_required_fields(dataset):
    mapping = dataset.mapping()
    props = mapping["mappings"]["properties"]
    required = {"id", "first_name", "last_name", "email", "age", "salary", "is_active"}
    assert required.issubset(props.keys())


def test_users_dataset_keyword_fields(dataset):
    props = dataset.mapping()["mappings"]["properties"]
    assert props["email"]["type"] == "keyword"
    assert props["country"]["type"] == "keyword"
    assert props["role"]["type"] == "keyword"


def test_users_dataset_text_fields_have_keyword_subfield(dataset):
    props = dataset.mapping()["mappings"]["properties"]
    assert props["first_name"]["type"] == "text"
    assert "keyword" in props["first_name"]["fields"]


# ── IndexProvisioner ──────────────────────────────────────────────────────────

def test_ensure_index_creates_when_not_exists(mock_es, dataset):
    mock_es.indices.exists.return_value = False
    provisioner = IndexProvisioner(mock_es)
    created = provisioner.ensure_index(dataset)
    assert created is True
    mock_es.indices.create.assert_called_once()


def test_ensure_index_skips_when_exists(mock_es, dataset):
    mock_es.indices.exists.return_value = True
    provisioner = IndexProvisioner(mock_es)
    created = provisioner.ensure_index(dataset)
    assert created is False
    mock_es.indices.create.assert_not_called()


def test_doc_count_returns_zero_on_error(mock_es, dataset):
    mock_es.count.side_effect = Exception("index missing")
    provisioner = IndexProvisioner(mock_es)
    assert provisioner.doc_count("users") == 0


# ── DataSeeder ────────────────────────────────────────────────────────────────

def test_seeder_calls_bulk(mock_es, dataset):
    with patch("esplay.domain.data_seeder.bulk", return_value=(87, [])) as mock_bulk:
        seeder = DataSeeder(mock_es)
        count = seeder.seed(dataset)
        assert count == 87
        mock_bulk.assert_called_once()


def test_seeder_raises_seed_error_on_failure(mock_es, dataset):
    with patch("esplay.domain.data_seeder.bulk", side_effect=Exception("bulk failed")):
        seeder = DataSeeder(mock_es)
        with pytest.raises(SeedError):
            seeder.seed(dataset)


def test_seeder_is_seeded_true_when_docs_exist(mock_es, dataset):
    mock_es.count.return_value = {"count": 87}
    seeder = DataSeeder(mock_es)
    assert seeder.is_seeded(dataset) is True


def test_seeder_is_seeded_false_when_empty(mock_es, dataset):
    mock_es.count.return_value = {"count": 0}
    seeder = DataSeeder(mock_es)
    assert seeder.is_seeded(dataset) is False
