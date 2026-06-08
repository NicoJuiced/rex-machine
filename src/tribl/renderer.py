"""Output renderers for tribl analysis reports."""

from __future__ import annotations

from pathlib import Path

from jinja2 import BaseLoader, Environment
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from tribl.models import Confidence, RepoQuality, RexReport

# Confidence level colors
_CONFIDENCE_COLORS = {
    Confidence.STRONGLY_INFERRED: "green",
    Confidence.PROBABLE: "blue",
    Confidence.CAUTIOUS_HYPOTHESIS: "yellow",
    Confidence.INSUFFICIENT_SIGNAL: "red",
}

_CONFIDENCE_LABELS = {
    Confidence.STRONGLY_INFERRED: "Strongly Inferred",
    Confidence.PROBABLE: "Probable",
    Confidence.CAUTIOUS_HYPOTHESIS: "Cautious Hypothesis",
    Confidence.INSUFFICIENT_SIGNAL: "Insufficient Signal",
}

_QUALITY_COLORS = {
    RepoQuality.GOOD: "green",
    RepoQuality.ACCEPTABLE: "yellow",
    RepoQuality.INSUFFICIENT: "red",
}

_QUALITY_LABELS = {
    RepoQuality.GOOD: "Good",
    RepoQuality.ACCEPTABLE: "Acceptable",
    RepoQuality.INSUFFICIENT: "Insufficient",
}


def render_console(report: RexReport) -> None:
    """Render the report to the console using Rich."""
    console = Console()

    # Header
    console.print()
    console.print(
        Panel(
            f"[bold]{report.repo_name}[/bold]\n"
            f"Path: {report.repo_path}\n"
            f"Analyzed: {report.analyzed_at}\n"
            f"Model: {report.model_used}\n"
            f"Files scanned: {report.files_scanned}",
            title="tribl Analysis Report",
            border_style="blue",
        )
    )

    # Quality
    quality_color = _QUALITY_COLORS.get(report.repo_quality, "white")
    quality_label = _QUALITY_LABELS.get(report.repo_quality, report.repo_quality.value)
    console.print(f"\nRepository Quality: [{quality_color}]{quality_label}[/{quality_color}]")

    # Warnings
    if report.warnings:
        console.print()
        for warning in report.warnings:
            console.print(f"  [yellow]Warning:[/yellow] {warning}")

    # Global Summary
    console.print()
    console.print(Panel(report.global_summary, title="Summary", border_style="cyan"))

    # Strengths
    if report.strengths:
        console.print()
        console.print("[bold green]Strengths:[/bold green]")
        for strength in report.strengths:
            console.print(f"  [green]+[/green] {strength}")

    # Improvement Suggestions
    if report.improvement_suggestions:
        console.print()
        console.print("[bold yellow]Improvement Suggestions:[/bold yellow]")
        for suggestion in report.improvement_suggestions:
            console.print(f"  [yellow]>[/yellow] {suggestion}")

    # REX Items
    if report.rex_items:
        console.print()
        console.print(f"[bold]REX Items ({len(report.rex_items)})[/bold]")
        console.print()

        for i, rex in enumerate(report.rex_items, 1):
            conf_color = _CONFIDENCE_COLORS.get(rex.confidence, "white")
            conf_label = _CONFIDENCE_LABELS.get(rex.confidence, rex.confidence.value)

            # REX header
            header = Text()
            header.append(f"REX #{i}: ", style="bold")
            header.append(rex.theme, style="bold cyan")
            header.append(" [", style="dim")
            header.append(conf_label, style=conf_color)
            header.append("]", style="dim")

            console.print(Panel(header, border_style="magenta"))

            # Context & Problem
            console.print(f"  [bold]Context:[/bold] {rex.context}")
            console.print(f"  [bold]Problem:[/bold] {rex.problem}")

            # Approaches table
            if rex.approaches:
                table = Table(title="Approaches", show_header=True, header_style="bold")
                table.add_column("Description", style="white", ratio=2)
                table.add_column("Worked?", justify="center", width=10)
                table.add_column("Details", style="dim", ratio=3)

                for approach in rex.approaches:
                    worked_str = (
                        "[green]Yes[/green]"
                        if approach.worked is True
                        else "[red]No[/red]"
                        if approach.worked is False
                        else "[dim]N/A[/dim]"
                    )
                    table.add_row(approach.description, worked_str, approach.details)

                console.print(table)

            # Result, Learning, Recommendation
            if rex.result:
                console.print(f"  [bold]Result:[/bold] {rex.result}")
            console.print(f"  [bold]Learning:[/bold] {rex.learning}")
            console.print(f"  [bold]Recommendation:[/bold] {rex.recommendation}")

            # Source files
            if rex.source_files:
                files_str = ", ".join(rex.source_files)
                console.print(f"  [bold]Source files:[/bold] [dim]{files_str}[/dim]")

            # Tags
            if rex.tags:
                tags_str = " ".join(f"[dim]#{tag}[/dim]" for tag in rex.tags)
                console.print(f"  [bold]Tags:[/bold] {tags_str}")

            console.print()
    else:
        console.print()
        console.print("[dim]No REX items were extracted from this repository.[/dim]")

    console.print()


def _load_template() -> str:
    """Load the Jinja2 markdown template."""
    template_path = Path(__file__).parent / "templates" / "report.md.j2"
    return template_path.read_text(encoding="utf-8")


def render_markdown(report: RexReport) -> str:
    """Render the report as a Markdown string using Jinja2."""
    template_str = _load_template()
    env = Environment(loader=BaseLoader(), autoescape=False)

    def _conf_label(c):
        return _CONFIDENCE_LABELS.get(c, c.value if hasattr(c, "value") else str(c))

    def _qual_label(q):
        return _QUALITY_LABELS.get(q, q.value if hasattr(q, "value") else str(q))

    env.filters["confidence_label"] = _conf_label
    env.filters["quality_label"] = _qual_label
    env.filters["worked_label"] = lambda w: "Yes" if w is True else ("No" if w is False else "N/A")

    template = env.from_string(template_str)
    return template.render(report=report)


def render_json(report: RexReport) -> str:
    """Render the report as a formatted JSON string."""
    return report.model_dump_json(indent=2)
