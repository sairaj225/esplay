"""DataSeeder — Repository pattern wrapper for bulk indexing.

Uses the Elasticsearch bulk helper for efficiency and reports progress
via an optional callback so the CLI layer can update a progress bar.
"""

from __future__ import annotations

from typing import Any, Callable, Iterator

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from esplay.datasets.base import DatasetProvider
from esplay.errors import SeedError


class DataSeeder:
    """Seeds an Elasticsearch index from a DatasetProvider."""

    def __init__(self, es: Elasticsearch) -> None:
        self._es = es

    def seed(
        self,
        dataset: DatasetProvider,
        *,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> int:
        """Bulk-index all documents from *dataset*.

        Args:
            dataset: Source of index name and documents.
            on_progress: Optional callback(indexed, total) called after each chunk.

        Returns:
            Total number of documents indexed.
        """
        docs = dataset.documents()
        total = len(docs)
        index_name = dataset.index_name()

        actions = [
            {
                "_index": index_name,
                "_id": doc.get("id"),
                "_source": doc,
            }
            for doc in docs
        ]

        try:
            indexed, errors = bulk(
                self._es,
                actions,
                chunk_size=50,
                raise_on_error=True,
                stats_only=False,
            )
            if on_progress:
                on_progress(indexed, total)
            return indexed
        except Exception as exc:
            raise SeedError(
                f"Failed to seed index {index_name!r}: {exc}",
                hint="Check cluster logs with `esplay logs`.",
            ) from exc

    def is_seeded(self, dataset: DatasetProvider) -> bool:
        """Return True if the index already contains documents."""
        try:
            result = self._es.count(index=dataset.index_name())
            return result["count"] > 0
        except Exception:
            return False
