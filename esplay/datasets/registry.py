"""Dataset registry — maps dataset names to DatasetProvider implementations.

To add a new dataset:
  1. Implement DatasetProvider in esplay/datasets/<name>.py.
  2. Add one line to _build_registry() below.
  3. Pass ``--dataset <name>`` to `esplay setup` (or set ESPLAY_DATASET).
"""

from __future__ import annotations

from esplay.datasets.base import DatasetProvider


def _build_registry() -> dict[str, type[DatasetProvider]]:
    from esplay.datasets.users import UsersDataset  # noqa: PLC0415

    return {
        "users": UsersDataset,
        # Future:
        # "products": ProductsDataset,
        # "logs": LogsDataset,
    }


def get_dataset(name: str) -> DatasetProvider:
    """Return a DatasetProvider instance for *name*."""
    registry = _build_registry()
    cls = registry.get(name)
    if cls is None:
        available = ", ".join(registry)
        raise ValueError(
            f"Unknown dataset {name!r}. Available: {available}."
        )
    return cls()
