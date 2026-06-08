"""CLI interface for rex-machine using Typer."""

from __future__ import annotations

import logging
import os
from enum import Enum
from pathlib import Path
from typing import Annotated

import anyio
import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from rex_machine import __version__
from rex_machine.agents import SUPPORTED_LANGS, Provider, run_analysis
from rex_machine.config import (
    DEFAULT_PROJECT_CONFIG,
    global_config_path,
    load_global,
    load_project,
    merge,
    save_global,
    save_project,
)
from rex_machine.models import RexReport
from rex_machine.renderer import render_console, render_json, render_markdown

app = typer.Typer(
    name="rex",
    help="Extract lessons learned (REX) from code repositories.",
    add_completion=False,
)

console = Console()


class OutputFormat(str, Enum):
    CONSOLE = "console"
    MARKDOWN = "markdown"
    JSON = "json"


# ─── Provider / Credential resolution ─────────────────────────────

_PROVIDER_MENU = [
    ("1", Provider.ANTHROPIC, "Anthropic", "Direct API key (console.anthropic.com)"),
    ("2", Provider.FOUNDRY, "Azure Foundry", "Claude via Azure AI Foundry"),
    ("3", Provider.BEDROCK, "AWS Bedrock", "Claude via Amazon Bedrock"),
    ("4", Provider.VERTEX, "Google Vertex", "Claude via Google Vertex AI"),
]


def _choose_provider() -> Provider:
    """Interactive provider selection menu (used by configure only)."""
    console.print()
    console.print("[bold]Choose your API provider:[/bold]\n")
    for key, _prov, name, desc in _PROVIDER_MENU:
        console.print(f"  [bold cyan]{key}[/bold cyan]  {name:18s} [dim]{desc}[/dim]")
    console.print()
    choice = Prompt.ask(
        "Provider",
        choices=[k for k, *_ in _PROVIDER_MENU],
        default="1",
        console=console,
    )
    return next(prov for k, prov, *_ in _PROVIDER_MENU if k == choice)


def _detect_provider(config: dict) -> Provider | None:
    """Auto-detect provider from env vars or saved config. No prompts."""
    if config.get("provider"):
        return Provider(config["provider"])
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return Provider.ANTHROPIC
    foundry_resource = os.environ.get("ANTHROPIC_FOUNDRY_RESOURCE", "").strip()
    foundry_key = os.environ.get("ANTHROPIC_FOUNDRY_API_KEY", "").strip()
    if foundry_resource and foundry_key:
        return Provider.FOUNDRY
    if os.environ.get("AWS_ACCESS_KEY_ID", "").strip():
        return Provider.BEDROCK
    if os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip():
        return Provider.VERTEX
    return None


def _resolve_credentials(provider: Provider, config: dict) -> dict:
    """Resolve credentials from env vars, saved config, or interactive prompt.

    Priority: env vars > saved config > ask interactively (first run).
    """
    if provider == Provider.ANTHROPIC:
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip() or config.get("anthropic_api_key", "")
        if not key:
            key = Prompt.ask(
                "[bold]Anthropic API key[/bold]",
                console=console,
                password=True,
            ).strip()
            if not key:
                _abort_missing("API key")
            _save_creds(config, anthropic_api_key=key)
        return {"api_key": key}

    if provider == Provider.FOUNDRY:
        resource = os.environ.get("ANTHROPIC_FOUNDRY_RESOURCE", "").strip() or config.get(
            "foundry_resource", ""
        )
        api_key = os.environ.get("ANTHROPIC_FOUNDRY_API_KEY", "").strip() or config.get(
            "foundry_api_key", ""
        )
        if not resource or not api_key:
            if not resource:
                resource = Prompt.ask(
                    "[bold]Foundry resource name[/bold] [dim](before .services.ai.azure.com)[/dim]",
                    console=console,
                ).strip()
            if not api_key:
                api_key = Prompt.ask(
                    "[bold]Foundry API key[/bold]",
                    console=console,
                    password=True,
                ).strip()
            if not resource or not api_key:
                _abort_missing("Foundry credentials")
            _save_creds(
                config,
                foundry_resource=resource,
                foundry_api_key=api_key,
            )
        return {"foundry_resource": resource, "foundry_api_key": api_key}

    if provider == Provider.BEDROCK:
        region = os.environ.get("AWS_REGION", "").strip() or config.get("aws_region", "")
        if not region:
            region = Prompt.ask(
                "[bold]AWS region[/bold]",
                default="us-east-1",
                console=console,
            ).strip()
            _save_creds(config, aws_region=region)
        return {"aws_region": region}

    if provider == Provider.VERTEX:
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip() or config.get(
            "gcp_project_id", ""
        )
        region = os.environ.get("GOOGLE_CLOUD_REGION", "").strip() or config.get("gcp_region", "")
        if not project:
            project = Prompt.ask(
                "[bold]GCP project ID[/bold]",
                console=console,
            ).strip()
            region = Prompt.ask(
                "[bold]GCP region[/bold]",
                default=region or "us-east5",
                console=console,
            ).strip()
            if not project:
                _abort_missing("GCP project")
            _save_creds(
                config,
                gcp_project_id=project,
                gcp_region=region,
            )
        return {"gcp_project_id": project, "gcp_region": region or "us-east5"}

    return {}


def _save_creds(config: dict, **creds: str) -> None:
    """Save credentials to global config (always — no 'save?' prompt)."""
    config.update(creds)
    save_global(config)
    console.print(f"[dim]Saved to {global_config_path()}[/dim]\n")


def _abort_missing(what: str) -> None:
    console.print(f"[bold red]No {what} provided.[/bold red]")
    raise typer.Exit(code=1)


# ─── Config display ──────────────────────────────────────────────


def _print_global_config(config: dict) -> None:
    table = Table(title="Global config", show_header=False, border_style="blue")
    table.add_column("Key", style="bold")
    table.add_column("Value")

    provider = config.get("provider", "anthropic")
    table.add_row("Provider", provider)
    table.add_row("Model", config.get("model", "(project default)"))

    if provider == "anthropic":
        key = config.get("anthropic_api_key", "")
        table.add_row("API Key", _mask(key))
    elif provider == "foundry":
        resource = config.get("foundry_resource", "(not set)")
        key = config.get("foundry_api_key", "")
        table.add_row("Resource", resource)
        table.add_row("Endpoint", f"https://{resource}.services.ai.azure.com/anthropic/")
        table.add_row("API Key", _mask(key))
    elif provider == "bedrock":
        table.add_row("AWS Region", config.get("aws_region", "us-east-1"))
    elif provider == "vertex":
        table.add_row("GCP Project", config.get("gcp_project_id", "(not set)"))
        table.add_row("GCP Region", config.get("gcp_region", "us-east5"))

    table.add_row("Config file", str(global_config_path()))
    console.print(table)


def _print_project_config(config: dict, path: Path) -> None:
    if not config:
        return
    title = f"Project config ({path}/.rex-machine.json)"
    table = Table(title=title, show_header=False, border_style="cyan")
    table.add_column("Key", style="bold")
    table.add_column("Value")
    for k, v in config.items():
        table.add_row(k, str(v))
    console.print(table)


def _mask(key: str) -> str:
    if len(key) > 16:
        return f"{key[:8]}...{key[-4:]}"
    if key:
        return "****"
    return "(not set)"


# ─── Commands ─────────────────────────────────────────────────────


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"rex v{__version__}")
        raise typer.Exit()


@app.callback()
def callback(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """rex - Extract lessons learned from code repositories."""


@app.command()
def configure() -> None:
    """Set up your API provider and credentials (saved globally)."""
    config = load_global()

    console.print(Panel("[bold]rex configure[/bold]", border_style="blue"))

    provider = _choose_provider()
    config["provider"] = provider.value

    if provider == Provider.ANTHROPIC:
        key = Prompt.ask("[bold]Anthropic API key[/bold]", console=console, password=True)
        config["anthropic_api_key"] = key.strip()

    elif provider == Provider.FOUNDRY:
        resource = Prompt.ask(
            "[bold]Foundry resource name[/bold] [dim](e.g. my-resource)[/dim]",
            default=config.get("foundry_resource", ""),
            console=console,
        )
        config["foundry_resource"] = resource.strip()
        key = Prompt.ask("[bold]Foundry API key[/bold]", console=console, password=True)
        config["foundry_api_key"] = key.strip()

    elif provider == Provider.BEDROCK:
        region = Prompt.ask(
            "[bold]AWS region[/bold]",
            default=config.get("aws_region", "us-east-1"),
            console=console,
        )
        config["aws_region"] = region.strip()
        console.print("[dim]AWS credentials: ~/.aws/credentials or env vars[/dim]")

    elif provider == Provider.VERTEX:
        project = Prompt.ask(
            "[bold]GCP project ID[/bold]",
            default=config.get("gcp_project_id", ""),
            console=console,
        )
        config["gcp_project_id"] = project.strip()
        region = Prompt.ask(
            "[bold]GCP region[/bold]",
            default=config.get("gcp_region", "us-east5"),
            console=console,
        )
        config["gcp_region"] = region.strip()
        console.print("[dim]GCP credentials: gcloud auth or env vars[/dim]")

    save_global(config)
    console.print(f"\n[green]Saved to {global_config_path()}[/green]\n")
    _print_global_config(config)


@app.command()
def init(
    path: Annotated[
        Path,
        typer.Argument(help="Project directory.", exists=True, resolve_path=True),
    ] = Path("."),
) -> None:
    """Create a .rex-machine.json config file in the project directory."""
    existing = load_project(path)
    config = {**DEFAULT_PROJECT_CONFIG, **existing}

    console.print(Panel("[bold]rex init[/bold]", border_style="cyan"))

    config["model"] = Prompt.ask(
        "Model",
        default=config.get("model", "claude-sonnet-4-6"),
        console=console,
    )
    config["output"] = Prompt.ask(
        "Default output format",
        choices=["console", "markdown", "json"],
        default=config.get("output", "console"),
        console=console,
    )
    config["max_tool_calls"] = int(
        Prompt.ask(
            "Max tool calls per agent",
            default=str(config.get("max_tool_calls", 30)),
            console=console,
        )
    )

    out = save_project(path, config)
    console.print(f"\n[green]Created {out}[/green]")
    console.print("[dim]Commit this file — it contains no secrets.[/dim]\n")
    _print_project_config(config, path)


@app.command()
def reset() -> None:
    """Reset all saved configuration (credentials + project settings)."""
    global_path = global_config_path()
    project_path = Path.cwd() / ".rex-machine.json"

    deleted = False
    if global_path.is_file():
        global_path.unlink()
        console.print(f"[green]Deleted[/green] {global_path}")
        deleted = True
    if project_path.is_file():
        project_path.unlink()
        console.print(f"[green]Deleted[/green] {project_path}")
        deleted = True

    if deleted:
        console.print("\n[dim]Run [bold]rex extract[/bold] to reconfigure.[/dim]")
    else:
        console.print("[dim]Nothing to reset — no configuration found.[/dim]")


@app.command()
def status(
    path: Annotated[
        Path,
        typer.Argument(help="Project directory.", exists=True, resolve_path=True),
    ] = Path("."),
) -> None:
    """Show current configuration (global + project)."""
    console.print()
    g = load_global()
    p = load_project(path)

    if not g and not p:
        console.print(
            "[dim]No configuration found.\n"
            "Run [bold]rex configure[/bold] to set up credentials.\n"
            "Run [bold]rex init[/bold] to create a project config.[/dim]"
        )
        raise typer.Exit()

    if g:
        _print_global_config(g)
    if p:
        console.print()
        _print_project_config(p, path)
    console.print()


@app.command()
def extract(
    path: Annotated[
        Path,
        typer.Argument(
            help="Path to the repository to extract REX from.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = Path("."),
    output: Annotated[
        OutputFormat | None,
        typer.Option("--output", "-o", help="Output format (overrides project config)."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Claude model (overrides config)."),
    ] = None,
    output_file: Annotated[
        Path | None,
        typer.Option("--output-file", "-f", help="Write output to a file."),
    ] = None,
    provider: Annotated[
        Provider | None,
        typer.Option("--provider", "-p", help="API provider (overrides config)."),
    ] = None,
    lang: Annotated[
        str,
        typer.Option("--lang", "-l", help="Output language: en (default) or fr."),
    ] = "en",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose logging."),
    ] = False,
) -> None:
    """Extract technical lessons learned (REX) from a code repository."""
    if lang not in SUPPORTED_LANGS:
        choices = ", ".join(sorted(SUPPORTED_LANGS))
        console.print(f"[bold red]Unsupported language: {lang}. Choose from: {choices}[/bold red]")
        raise typer.Exit(code=1)

    log_level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )

    config = merge(Path.cwd())
    global_cfg = load_global()

    if provider:
        effective_provider = provider
    else:
        detected = _detect_provider(global_cfg)
        if detected:
            effective_provider = detected
        else:
            console.print("\n[bold yellow]First run — let's set up your API access.[/bold yellow]")
            effective_provider = _choose_provider()
            global_cfg["provider"] = effective_provider.value

    effective_model = model or config.get("model", "claude-sonnet-4-6")
    effective_output = output or OutputFormat(config.get("output", "console"))
    max_tool_calls = config.get("max_tool_calls", 30)

    creds = _resolve_credentials(effective_provider, global_cfg)

    repo_path = str(path)

    console.print(f"\n[bold blue]rex[/bold blue] v{__version__}")
    console.print(f"Analyzing: [cyan]{repo_path}[/cyan]")
    console.print(f"Model: [cyan]{effective_model}[/cyan]")
    console.print(f"Provider: [cyan]{effective_provider.value}[/cyan]")
    if lang != "en":
        console.print(f"Language: [cyan]{lang}[/cyan]")
    console.print()

    try:

        async def _run() -> RexReport:
            return await run_analysis(
                repo_path,
                effective_model,
                provider=effective_provider,
                max_tool_calls=max_tool_calls,
                lang=lang,
                **creds,
            )

        with console.status("[bold green]Analyzing repository...", spinner="dots"):
            report = anyio.run(_run)
    except KeyboardInterrupt:
        console.print("\n[yellow]Analysis cancelled.[/yellow]")
        raise typer.Exit(code=130)
    except BaseException as exc:
        # Unwrap ExceptionGroup → first cause only (except* requires Python 3.11+)
        cause = exc
        while hasattr(cause, "exceptions"):
            cause = cause.exceptions[0]
        console.print(f"\n[bold red]Error:[/bold red] {cause}")
        if verbose:
            console.print_exception()
        raise typer.Exit(code=1)

    if effective_output == OutputFormat.CONSOLE:
        if output_file:
            console.print("[yellow]Note:[/yellow] Using markdown for file output.")
            _write_file(output_file, render_markdown(report))
        else:
            render_console(report)
    elif effective_output == OutputFormat.MARKDOWN:
        result = render_markdown(report)
        if output_file:
            _write_file(output_file, result)
        else:
            console.print(Markdown(result))
    elif effective_output == OutputFormat.JSON:
        result = render_json(report)
        if output_file:
            _write_file(output_file, result)
        else:
            console.print_json(result)


def _write_file(path: Path, content: str) -> None:
    try:
        path.write_text(content, encoding="utf-8")
        console.print(f"[green]Report written to:[/green] {path}")
    except OSError as exc:
        console.print(f"[bold red]Error writing file:[/bold red] {exc}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
