"""Typed, layered configuration for esplay.

Precedence (lowest → highest):
  1. Hardcoded defaults (field defaults below)
  2. Config file  (~/.esplay/config.json — not yet implemented but slot exists)
  3. Environment variables  (prefix ESPLAY_)
  4. CLI flags  (applied after construction by the CLI layer)

Uses pydantic-settings so every field is validated and type-coerced.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EsplayConfig(BaseSettings):
    """All runtime-configurable values for esplay.

    Environment variable name = ESPLAY_ + field name upper-cased, e.g.
      ESPLAY_ES_PORT=9300
    """

    model_config = SettingsConfigDict(
        env_prefix="ESPLAY_",
        env_file=None,  # no .env loading by default; users set vars in their shell
        case_sensitive=False,
        extra="ignore",
    )

    # ── Stack versions ───────────────────────────────────────────────────────
    # IMPORTANT: ES and Kibana MUST share the same version — a single value
    # ensures they can never drift.
    stack_version: str = Field(
        default="8.13.4",
        description="Elasticsearch AND Kibana image version (must match).",
    )

    # ── Networking ───────────────────────────────────────────────────────────
    es_port: int = Field(default=9200, description="Host port for Elasticsearch.")
    kibana_port: int = Field(default=5601, description="Host port for Kibana.")

    # ── Feature flags ────────────────────────────────────────────────────────
    with_kibana: bool = Field(
        default=True,
        description="Launch Kibana alongside Elasticsearch.",
    )

    # ── Container naming ─────────────────────────────────────────────────────
    es_container_name: str = Field(
        default="esplay-elasticsearch",
        description="Name of the Elasticsearch container.",
    )
    kibana_container_name: str = Field(
        default="esplay-kibana",
        description="Name of the Kibana container.",
    )
    network_name: str = Field(
        default="esplay-net",
        description="Name of the shared Docker bridge network.",
    )
    volume_name: str = Field(
        default="esplay-es-data",
        description="Named Docker volume for ES data persistence.",
    )

    # ── JVM ─────────────────────────────────────────────────────────────────
    es_heap_size: str = Field(
        default="512m",
        description="Elasticsearch heap (both -Xms and -Xmx are set to this).",
    )

    # ── Health-check timeouts ────────────────────────────────────────────────
    es_health_timeout: int = Field(
        default=120,
        description="Seconds to wait for Elasticsearch to become healthy.",
    )
    kibana_health_timeout: int = Field(
        default=180,
        description="Seconds to wait for Kibana to become available.",
    )
    health_poll_interval: float = Field(
        default=3.0,
        description="Seconds between health-check polls.",
    )

    # ── Dataset ──────────────────────────────────────────────────────────────
    dataset: str = Field(
        default="users",
        description="Name of the dataset to seed (must be registered in datasets/registry.py).",
    )

    # ── Local state dir ──────────────────────────────────────────────────────
    state_dir: Path = Field(
        default=Path.home() / ".esplay",
        description="Directory where esplay stores runtime state and credentials.",
    )

    # ── Labels ───────────────────────────────────────────────────────────────
    container_label: dict[str, str] = Field(
        default={"app": "esplay"},
        description="Docker labels applied to every managed container.",
    )

    # ── Derived helpers (not settings) ───────────────────────────────────────

    @property
    def es_image(self) -> str:
        return f"docker.elastic.co/elasticsearch/elasticsearch:{self.stack_version}"

    @property
    def kibana_image(self) -> str:
        return f"docker.elastic.co/kibana/kibana:{self.stack_version}"

    @property
    def es_url(self) -> str:
        return f"http://localhost:{self.es_port}"

    @property
    def kibana_url(self) -> str:
        return f"http://localhost:{self.kibana_port}"

    @property
    def kibana_devtools_url(self) -> str:
        return f"http://localhost:{self.kibana_port}/app/dev_tools#/console"

    @property
    def state_file(self) -> Path:
        return self.state_dir / "state.json"
