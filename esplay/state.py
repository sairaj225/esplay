"""Persisted runtime state for esplay.

Saved to ~/.esplay/state.json with mode 0o600 (owner read/write only)
so credentials are not world-readable.

The state layer is intentionally thin — it only stores data that cannot
be re-derived from the running containers (primarily the generated passwords).
"""

from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from esplay.errors import StateError


class EsplayState(BaseModel):
    """Persisted state written after a successful `esplay setup`."""

    elastic_password: str = ""
    kibana_system_password: str = ""
    es_container_id: str = ""
    kibana_container_id: str = ""
    network_id: str = ""
    stack_version: str = ""
    es_port: int = 9200
    kibana_port: int = 5601
    with_kibana: bool = True
    doc_count: int = 0


class StateManager:
    """Reads and writes the esplay state file."""

    def __init__(self, state_file: Path) -> None:
        self._path = state_file

    def load(self) -> EsplayState:
        """Load state from disk.  Returns an empty state if file does not exist."""
        if not self._path.exists():
            return EsplayState()
        try:
            data = json.loads(self._path.read_text())
            return EsplayState(**data)
        except Exception as exc:
            raise StateError(
                f"Cannot read state file {self._path}: {exc}",
                hint="Delete ~/.esplay/state.json and re-run `esplay setup`.",
            ) from exc

    def save(self, state: EsplayState) -> None:
        """Persist state to disk with restrictive permissions."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(state.model_dump_json(indent=2))
            # chmod 600 — owner read/write only
            self._path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except Exception as exc:
            raise StateError(
                f"Cannot write state file {self._path}: {exc}",
            ) from exc

    def clear(self) -> None:
        """Delete the state file (called on destroy)."""
        if self._path.exists():
            try:
                self._path.unlink()
            except OSError as exc:
                raise StateError(
                    f"Cannot delete state file {self._path}: {exc}",
                ) from exc

    def is_setup(self) -> bool:
        """Return True if there is saved state indicating a running cluster."""
        state = self.load()
        return bool(state.elastic_password and state.es_container_id)
