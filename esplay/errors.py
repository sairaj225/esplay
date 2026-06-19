"""Custom exception hierarchy for esplay.

Every error that esplay raises is a subclass of EsplayError so callers can
catch everything with a single except clause.  Each subclass carries a
human-readable message *and* an exit code so the CLI layer can exit with
a distinct code per failure category.
"""

from __future__ import annotations


class EsplayError(Exception):
    """Base class for all esplay errors."""

    exit_code: int = 1

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        # 'hint' is shown to the user as the "what to do next" line.
        self.hint = hint


# ── Docker / runtime ────────────────────────────────────────────────────────

class DockerNotFoundError(EsplayError):
    """Docker (or the chosen container runtime) is not installed."""

    exit_code = 2

    def __init__(self) -> None:
        super().__init__(
            "Docker is not installed.",
            hint=(
                "Run `esplay setup` again after installing Docker Desktop "
                "(https://www.docker.com/products/docker-desktop) or let "
                "esplay install it for you via Homebrew."
            ),
        )


class DaemonNotRunningError(EsplayError):
    """Docker daemon is installed but not running."""

    exit_code = 3

    def __init__(self) -> None:
        super().__init__(
            "Docker daemon is not running.",
            hint="Start Docker Desktop and re-run `esplay setup`.",
        )


class ImagePullError(EsplayError):
    """Could not pull a required Docker image."""

    exit_code = 4


class ContainerStartError(EsplayError):
    """Failed to start a container."""

    exit_code = 5


class NetworkError(EsplayError):
    """Failed to create/remove the Docker network."""

    exit_code = 6


# ── Elasticsearch / cluster ──────────────────────────────────────────────────

class ClusterUnhealthyError(EsplayError):
    """Cluster did not become healthy within the timeout."""

    exit_code = 10

    def __init__(self, timeout: int) -> None:
        super().__init__(
            f"Elasticsearch did not become healthy within {timeout}s.",
            hint=(
                "Check container logs with `esplay logs` and ensure Docker "
                "has enough memory (≥2 GB recommended)."
            ),
        )


class SeedError(EsplayError):
    """Data seeding failed."""

    exit_code = 11


class IndexError(EsplayError):  # noqa: A001  (shadows built-in intentionally)
    """Index provisioning failed."""

    exit_code = 12


# ── Kibana ───────────────────────────────────────────────────────────────────

class KibanaUnhealthyError(EsplayError):
    """Kibana did not become available within the timeout."""

    exit_code = 20

    def __init__(self, timeout: int) -> None:
        super().__init__(
            f"Kibana did not become available within {timeout}s.",
            hint=(
                "Check Kibana logs with `esplay logs --service kibana`. "
                "Kibana can take up to 60 s on first start — try increasing "
                "kibana_health_timeout in your config."
            ),
        )


# ── Platform ─────────────────────────────────────────────────────────────────

class UnsupportedPlatformError(EsplayError):
    """The current OS is not yet supported."""

    exit_code = 30

    def __init__(self, os_name: str) -> None:
        super().__init__(
            f"esplay does not yet support {os_name}.",
            hint=(
                "Contributions welcome! Implement PlatformProvider for your OS "
                "and register it in esplay/platform/factory.py."
            ),
        )


# ── State ────────────────────────────────────────────────────────────────────

class StateError(EsplayError):
    """Problem reading or writing local state."""

    exit_code = 40


class NotSetupError(EsplayError):
    """Command requires a running cluster that does not exist yet."""

    exit_code = 41

    def __init__(self) -> None:
        super().__init__(
            "No esplay cluster is running.",
            hint="Run `esplay setup` first.",
        )
