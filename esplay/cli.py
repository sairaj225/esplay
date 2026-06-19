"""esplay CLI — Typer app wiring all commands and Rich output rendering.

This is the thin CLI layer: parse args, drive services, render output.
No domain or runtime logic lives here.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import Annotated, Optional

import questionary
import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from esplay import __version__
from esplay.config import EsplayConfig
from esplay.errors import EsplayError
from esplay.platform.factory import PlatformFactory
from esplay.runtime.factory import RuntimeFactory
from esplay.services.setup_service import SetupProgress, SetupService
from esplay.services.status_service import StatusService
from esplay.services.teardown_service import TeardownService
from esplay.state import StateManager

console = Console()
err_console = Console(stderr=True)

app = typer.Typer(
    name="esplay",
    help="[bold]esplay[/bold] — Elasticsearch learning playground 🔍",
    rich_markup_mode="rich",
    no_args_is_help=True,
    add_completion=True,
)

# ── Global options ────────────────────────────────────────────────────────────

_yes_opt = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts.")
_quiet_opt = typer.Option(False, "--quiet", "-q", help="Suppress non-essential output.")
_debug_opt = typer.Option(False, "--debug", "--verbose", help="Show full stack traces.")
_no_kibana_opt = typer.Option(None, "--no-kibana", help="Skip Kibana (ES-only mode).")
_with_kibana_opt = typer.Option(None, "--with-kibana", help="Include Kibana (default).")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_config(**overrides) -> EsplayConfig:
    cfg = EsplayConfig()
    for k, v in overrides.items():
        if v is not None:
            object.__setattr__(cfg, k, v)
    return cfg


def _get_runtime():
    return RuntimeFactory.get("docker")


def _get_platform():
    return PlatformFactory.get()


def _state_manager(cfg: EsplayConfig) -> StateManager:
    return StateManager(cfg.state_file)


@contextmanager
def _handle_errors(debug: bool = False):
    try:
        yield
    except EsplayError as exc:
        err_console.print(f"\n[bold red]Error:[/bold red] {exc.message}")
        if exc.hint:
            err_console.print(f"[yellow]Hint:[/yellow] {exc.hint}")
        if debug:
            err_console.print_exception()
        raise typer.Exit(exc.exit_code)
    except KeyboardInterrupt:
        err_console.print("\n[yellow]Interrupted.[/yellow]")
        raise typer.Exit(130)
    except Exception as exc:
        err_console.print(f"\n[bold red]Unexpected error:[/bold red] {exc}")
        if debug:
            err_console.print_exception()
        else:
            err_console.print("Run with [bold]--debug[/bold] for a full traceback.")
        raise typer.Exit(1)


# ── Rich progress adapter ─────────────────────────────────────────────────────

class _RichProgress(SetupProgress):
    """Bridges SetupService callbacks to Rich terminal output."""

    def __init__(self, quiet: bool = False) -> None:
        self._quiet = quiet
        self._spinner: Progress | None = None
        self._spinner_task = None

    def step(self, message: str) -> None:
        self._stop_spinner()
        if not self._quiet:
            console.print(f"[cyan]→[/cyan] {message}")

    def success(self, message: str) -> None:
        self._stop_spinner()
        if not self._quiet:
            console.print(f"[green]✓[/green] {message}")

    def warning(self, message: str) -> None:
        self._stop_spinner()
        if not self._quiet:
            console.print(f"[yellow]⚠[/yellow] {message}")

    def spinner_start(self, message: str) -> None:
        self._spinner = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        )
        self._spinner.start()
        self._spinner_task = self._spinner.add_task(message)

    def spinner_stop(self, success: bool = True, message: str = "") -> None:
        self._stop_spinner()
        if message and not self._quiet:
            icon = "[green]✓[/green]" if success else "[red]✗[/red]"
            console.print(f"{icon} {message}")

    def progress(self, done: int, total: int) -> None:
        if not self._quiet:
            console.print(f"[green]✓[/green] Indexed {done}/{total} documents")

    def _stop_spinner(self) -> None:
        if self._spinner:
            self._spinner.stop()
            self._spinner = None


# ── Commands ──────────────────────────────────────────────────────────────────

@app.command(name="setup")
@app.command(name="create-db", hidden=True)
def setup(
    yes: bool = _yes_opt,
    quiet: bool = _quiet_opt,
    debug: bool = _debug_opt,
    no_kibana: Annotated[Optional[bool], typer.Option("--no-kibana/--with-kibana")] = None,
) -> None:
    """[bold]Provision a local Elasticsearch + Kibana playground.[/bold]

    Pulls images, starts containers, seeds a [cyan]users[/cyan] index,
    and prints ready-to-use credentials and sample queries.
    """
    with_kibana = True if no_kibana is None else (not no_kibana)

    with _handle_errors(debug):
        cfg = _build_config(with_kibana=with_kibana)
        runtime = _get_runtime()
        platform = _get_platform()
        state = _state_manager(cfg)
        progress = _RichProgress(quiet=quiet)

        if not quiet:
            console.print(
                Panel.fit(
                    f"[bold cyan]esplay[/bold cyan] v{__version__}  •  "
                    f"Elasticsearch {cfg.stack_version}",
                    title="Setting up your playground",
                    border_style="cyan",
                )
            )

        svc = SetupService(cfg, platform, runtime, state, progress)
        final_state = svc.run()

        _print_credentials_panel(cfg, final_state)
        _print_sample_queries()


@app.command(name="destroy")
@app.command(name="destroy-db", hidden=True)
def destroy(
    yes: bool = _yes_opt,
    purge: bool = typer.Option(False, "--purge", help="Also remove the data volume."),
    debug: bool = _debug_opt,
) -> None:
    """[bold]Stop and remove the Elasticsearch + Kibana containers.[/bold]

    Use [bold]--purge[/bold] to also delete the data volume.
    """
    with _handle_errors(debug):
        cfg = _build_config()

        if not yes:
            confirmed = questionary.confirm(
                "This will stop and remove all esplay containers. Continue?",
                default=False,
            ).ask()
            if not confirmed:
                console.print("[yellow]Aborted.[/yellow]")
                raise typer.Exit(0)

        purge_volume = purge
        if not purge and not yes:
            purge_volume = questionary.confirm(
                f"Also delete the data volume '{cfg.volume_name}'?",
                default=False,
            ).ask()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as progress:
            task = progress.add_task("Tearing down …")
            svc = TeardownService(cfg, RuntimeFactory.get("docker"), _state_manager(cfg))
            svc.run(purge_volume=purge_volume)
            progress.update(task, description="Done")

        console.print("[green]✓[/green] All esplay resources removed.")
        if purge_volume:
            console.print(f"[green]✓[/green] Data volume [bold]{cfg.volume_name}[/bold] deleted.")


@app.command(name="status")
def status(debug: bool = _debug_opt) -> None:
    """[bold]Show the current state of your playground.[/bold]"""
    with _handle_errors(debug):
        cfg = _build_config()
        svc = StatusService(cfg, RuntimeFactory.get("docker"), _state_manager(cfg))
        ps = svc.run()

        _health_color = {
            "green": "green",
            "yellow": "yellow",
            "red": "red",
            "unreachable": "dim",
        }

        table = Table(
            title="esplay Playground Status",
            box=box.ROUNDED,
            border_style="cyan",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Component", style="bold")
        table.add_column("Container")
        table.add_column("Health / Status")
        table.add_column("URL")

        es_status_str = f"[{'green' if ps.es_running else 'red'}]{ps.es_container_status}[/]"
        es_health_str = f"[{_health_color.get(ps.cluster_health, 'dim')}]{ps.cluster_health}[/]"
        table.add_row(
            "Elasticsearch",
            es_status_str,
            es_health_str,
            ps.es_url,
        )

        if cfg.with_kibana:
            kb_color = "green" if ps.kibana_running else "red"
            kb_health_color = "green" if ps.kibana_available else "yellow"
            table.add_row(
                "Kibana",
                f"[{kb_color}]{ps.kibana_container_status}[/]",
                f"[{kb_health_color}]{ps.kibana_status}[/]",
                ps.kibana_url,
            )

        table.add_row(
            "users index",
            "—",
            f"{ps.doc_count} docs",
            "—",
        )

        console.print(table)

        if ps.state.elastic_password:
            console.print(
                f"\n[dim]Credentials: username=[bold]elastic[/bold]  "
                f"Run [bold]esplay credentials[/bold] to show the password.[/dim]"
            )


@app.command(name="credentials")
def credentials(debug: bool = _debug_opt) -> None:
    """[bold]Re-display saved credentials and connection strings.[/bold]"""
    with _handle_errors(debug):
        cfg = _build_config()
        state_mgr = _state_manager(cfg)
        saved = state_mgr.load()

        if not saved.elastic_password:
            console.print(
                "[yellow]No credentials found. Run [bold]esplay setup[/bold] first.[/yellow]"
            )
            raise typer.Exit(1)

        _print_credentials_panel(cfg, saved)


@app.command(name="open")
def open_kibana(debug: bool = _debug_opt) -> None:
    """[bold]Open Kibana Dev Tools in your default browser.[/bold]"""
    with _handle_errors(debug):
        cfg = _build_config()
        platform = _get_platform()
        url = cfg.kibana_devtools_url
        console.print(f"Opening [link={url}]{url}[/link] …")
        platform.open_url(url)


@app.command(name="logs")
def logs(
    service: Annotated[
        str,
        typer.Option("--service", "-s", help="Which service to tail: es or kibana"),
    ] = "es",
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output."),
    tail: int = typer.Option(100, "--tail", "-n", help="Number of recent lines to show."),
    debug: bool = _debug_opt,
) -> None:
    """[bold]Stream container logs.[/bold]"""
    with _handle_errors(debug):
        cfg = _build_config()
        runtime = _get_runtime()

        name_map = {
            "es": cfg.es_container_name,
            "kibana": cfg.kibana_container_name,
        }
        container_name = name_map.get(service)
        if container_name is None:
            err_console.print(f"[red]Unknown service {service!r}. Use 'es' or 'kibana'.[/red]")
            raise typer.Exit(1)

        console.print(f"[cyan]Logs for [bold]{service}[/bold] (Ctrl-C to stop):[/cyan]")
        try:
            for line in runtime.logs(container_name, follow=follow, tail=tail):
                console.print(line, highlight=False)
        except KeyboardInterrupt:
            pass


@app.command(name="reset")
def reset(
    yes: bool = _yes_opt,
    debug: bool = _debug_opt,
) -> None:
    """[bold]Destroy everything and set up fresh.[/bold]"""
    with _handle_errors(debug):
        if not yes:
            confirmed = questionary.confirm(
                "This will destroy your current playground and recreate it from scratch. Continue?",
                default=False,
            ).ask()
            if not confirmed:
                console.print("[yellow]Aborted.[/yellow]")
                raise typer.Exit(0)

        # Destroy
        cfg = _build_config()
        svc = TeardownService(cfg, RuntimeFactory.get("docker"), _state_manager(cfg))
        svc.run(purge_volume=True)
        console.print("[green]✓[/green] Destroyed. Setting up fresh …\n")

    # Re-run setup (separate error context for clarity)
    ctx = typer.get_current_context()
    ctx.invoke(setup, yes=True)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"esplay {__version__}")
        raise typer.Exit(0)


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """esplay — Elasticsearch learning playground."""


# ── Output helpers ─────────────────────────────────────────────────────────────

def _print_credentials_panel(cfg: EsplayConfig, state) -> None:
    """Render the 'Your playground is ready' credentials panel."""
    password = state.elastic_password
    doc_count = getattr(state, "doc_count", 0)

    kibana_line = (
        f"[bold green]Kibana Dev Tools[/bold green] : {cfg.kibana_devtools_url}  ← run your queries here"
        if cfg.with_kibana
        else "[dim]Kibana       : disabled (--no-kibana)[/dim]"
    )

    panel_text = "\n".join([
        kibana_line,
        f"[cyan]Kibana URL[/cyan]       : {cfg.kibana_url}",
        f"[cyan]Elasticsearch[/cyan]    : {cfg.es_url}",
        "",
        f"[bold]Username[/bold]         : elastic",
        f"[bold yellow]Password[/bold yellow]         : {password}",
        "",
        f"[dim]Index[/dim]            : users  ({doc_count} docs)",
        f"[dim]Stack version[/dim]    : {cfg.stack_version}",
    ])

    console.print()
    console.print(
        Panel(
            panel_text,
            title="[bold green]Your playground is ready! 🎉[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )


def _print_sample_queries() -> None:
    """Print ready-to-paste Kibana Dev Tools sample queries."""
    queries = '''
[bold cyan]Try these in Kibana Dev Tools (copy & paste):[/bold cyan]

[bold]# 1. Full-text search[/bold]
GET users/_search
{
  "query": { "match": { "first_name": "Alice" } }
}

[bold]# 2. Range filter — active users aged 25–35[/bold]
GET users/_search
{
  "query": {
    "bool": {
      "must": { "term": { "is_active": true } },
      "filter": { "range": { "age": { "gte": 25, "lte": 35 } } }
    }
  }
}

[bold]# 3. Aggregation — avg salary by department[/bold]
GET users/_search
{
  "size": 0,
  "aggs": {
    "by_department": {
      "terms": { "field": "department" },
      "aggs": { "avg_salary": { "avg": { "field": "salary" } } }
    }
  }
}

[bold]# 4. Bool query — Engineers in the US earning > $100k[/bold]
GET users/_search
{
  "query": {
    "bool": {
      "must": [
        { "term": { "role": "Engineer" } },
        { "term": { "country": "US" } }
      ],
      "filter": { "range": { "salary": { "gt": 100000 } } }
    }
  },
  "sort": [{ "salary": "desc" }]
}

[dim]curl equivalent (option B):
curl -s -u elastic:<password> http://localhost:9200/users/_search \\
  -H 'Content-Type: application/json' \\
  -d '{"query":{"match_all":{}}}' | python3 -m json.tool[/dim]
'''
    console.print(Panel(queries, title="Sample Queries", border_style="blue", padding=(0, 1)))


if __name__ == "__main__":
    app()
