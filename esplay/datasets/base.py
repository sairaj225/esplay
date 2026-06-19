"""DatasetProvider — extension seam for seed datasets.

To add a new dataset (e.g. 'products', 'logs'):
  1. Create esplay/datasets/<name>.py implementing DatasetProvider.
  2. Register it in esplay/datasets/registry.py.
  3. No other files need changing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DatasetProvider(ABC):
    """Interface for a seed dataset.

    This is an intentional extension seam.  IndexProvisioner and DataSeeder
    use this interface — they must not import concrete dataset classes directly.
    """

    @abstractmethod
    def index_name(self) -> str:
        """Elasticsearch index name to create and seed."""

    @abstractmethod
    def mapping(self) -> dict[str, Any]:
        """Explicit index mapping body (passed to indices.create)."""

    @abstractmethod
    def documents(self) -> list[dict[str, Any]]:
        """List of documents to bulk-index.  Each dict becomes one ES document."""
