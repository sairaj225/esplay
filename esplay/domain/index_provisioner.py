"""IndexProvisioner — Repository pattern wrapper for ES index operations.

The rest of the app never calls the ES client directly; it goes through this
class.  Swap the client (e.g. move to async) by changing only this file.
"""

from __future__ import annotations

from typing import Any

from elasticsearch import Elasticsearch

from esplay.datasets.base import DatasetProvider
from esplay.errors import IndexError  # noqa: A004


class IndexProvisioner:
    """Creates and manages Elasticsearch indices."""

    def __init__(self, es: Elasticsearch) -> None:
        self._es = es

    def ensure_index(self, dataset: DatasetProvider) -> bool:
        """Create the index if it doesn't already exist.

        Returns True if the index was created, False if it already existed.
        """
        name = dataset.index_name()
        if self._es.indices.exists(index=name):
            return False
        try:
            self._es.indices.create(index=name, body=dataset.mapping())
            return True
        except Exception as exc:
            raise IndexError(
                f"Failed to create index {name!r}: {exc}",
                hint="Check cluster logs with `esplay logs`.",
            ) from exc

    def delete_index(self, index_name: str) -> None:
        """Delete an index (no-op if it doesn't exist)."""
        if self._es.indices.exists(index=index_name):
            self._es.indices.delete(index=index_name)

    def doc_count(self, index_name: str) -> int:
        """Return the number of documents in *index_name*, or 0 if missing."""
        try:
            result = self._es.count(index=index_name)
            return result["count"]
        except Exception:
            return 0
