"""Agentic pipeline for tribl analysis using the Anthropic SDK.

Each sub-agent runs an autonomous tool-use loop where Claude navigates
the repository by calling tools (list_files, read_file, grep), similar
to how Claude Code explores a codebase.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import anthropic
import anyio
from jinja2 import Environment, FileSystemLoader

from tribl.models import RepoQuality, RexReport
from tribl.scanner import SKIP_DIRS, RepoMap, scan_repo

logger = logging.getLogger("tribl")

SUBAGENT_MAX_TOKENS = 4096
SYNTHESIS_MAX_TOKENS = 8192
DEFAULT_MAX_TOOL_CALLS = 30

LANG_NAMES = {"en": "English", "fr": "French"}

# ─── Prompt templates ────────────────────────────────────────────

_TEMPLATE_DIR = Path(__file__).parent / "templates" / "prompts"
_jinja = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    keep_trailing_newline=False,
    autoescape=False,
)


def _load_prompt(name: str, **kwargs: object) -> str:
    return _jinja.get_template(f"{name}.j2").render(**kwargs).strip()


# ─── Provider / Client ───────────────────────────────────────────


class Provider(str, Enum):
    ANTHROPIC = "anthropic"
    FOUNDRY = "foundry"
    BEDROCK = "bedrock"
    VERTEX = "vertex"


AsyncClient = (
    anthropic.AsyncAnthropic | anthropic.AsyncAnthropicBedrock | anthropic.AsyncAnthropicVertex
)


def create_client(
    provider: Provider = Provider.ANTHROPIC,
    *,
    api_key: str | None = None,
    foundry_resource: str | None = None,
    foundry_api_key: str | None = None,
    aws_region: str | None = None,
    gcp_project_id: str | None = None,
    gcp_region: str | None = None,
) -> AsyncClient:
    """Create the appropriate async client for the chosen provider."""
    if provider == Provider.FOUNDRY:
        resource = foundry_resource or ""
        base_url = f"https://{resource}.services.ai.azure.com/anthropic/"
        return anthropic.AsyncAnthropic(
            api_key=foundry_api_key or "placeholder",
            base_url=base_url,
            default_headers={"api-key": foundry_api_key or ""},
        )
    if provider == Provider.BEDROCK:
        return anthropic.AsyncAnthropicBedrock(
            aws_region=aws_region or "us-east-1",
        )
    if provider == Provider.VERTEX:
        return anthropic.AsyncAnthropicVertex(
            project_id=gcp_project_id or "",
            region=gcp_region or "us-east5",
        )
    return anthropic.AsyncAnthropic(api_key=api_key)


# ─── Tool definitions (JSON Schema for Claude) ──────────────────


REPO_TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_files",
        "description": (
            "List files and directories at a path in the repository. "
            "Use 'pattern' for glob matching (e.g. '*.py', '**/*.test.ts')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative directory path. Defaults to repo root.",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g. '*.py').",
                },
            },
            "required": [],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read the contents of a file. Returns text with line numbers. "
            "For large files, use start_line/end_line to read a section."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative file path within the repository.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "First line to read (1-based).",
                    "minimum": 1,
                },
                "end_line": {
                    "type": "integer",
                    "description": "Last line to read (inclusive).",
                    "minimum": 1,
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "grep",
        "description": (
            "Search for a text or regex pattern across files. "
            "Returns matching lines with file paths and line numbers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Text or regex pattern to search for.",
                },
                "path": {
                    "type": "string",
                    "description": "Restrict search to this subdirectory.",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Glob to filter file types (e.g. '*.py').",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max matches to return (default 50, max 100).",
                    "default": 50,
                    "maximum": 100,
                },
            },
            "required": ["pattern"],
        },
    },
]


# ─── Tool executor (read-only, scoped to repo) ──────────────────


class ToolExecutor:
    """Executes repository exploration tools. All operations are read-only."""

    def __init__(self, repo_path: str) -> None:
        self.root = Path(repo_path).resolve()

    def _safe_path(self, relative: str) -> Path:
        """Resolve a path safely within the repo root."""
        cleaned = relative.replace("\\", "/").lstrip("/")
        resolved = (self.root / cleaned).resolve()
        if not str(resolved).startswith(str(self.root)):
            raise ValueError(f"Path outside repository: {relative}")
        return resolved

    def execute(self, name: str, input_data: dict[str, Any]) -> str:
        """Execute a tool call and return the result string."""
        dispatch = {
            "list_files": self._list_files,
            "read_file": self._read_file,
            "grep": self._grep,
        }
        handler = dispatch.get(name)
        if not handler:
            return f"Unknown tool: {name}"
        try:
            return handler(input_data)
        except Exception as exc:
            return f"Error: {exc}"

    def _list_files(self, data: dict[str, Any]) -> str:
        path = data.get("path", ".")
        pattern = data.get("pattern")
        target = self._safe_path(path)

        if not target.is_dir():
            return f"Not a directory: {path}"

        entries: list[str] = []
        if pattern:
            for match in sorted(target.rglob(pattern)):
                rel = str(match.relative_to(self.root)).replace("\\", "/")
                if match.is_dir():
                    entries.append(f"  {rel}/")
                else:
                    try:
                        size = match.stat().st_size
                        entries.append(f"  {rel}  ({size:,} bytes)")
                    except OSError:
                        entries.append(f"  {rel}")
                if len(entries) >= 200:
                    entries.append("  ... (capped at 200)")
                    break
            if not entries:
                return f"No files matching '{pattern}' in {path}/"
            return f"Files matching '{pattern}' in {path}/:\n" + "\n".join(entries)

        for item in sorted(target.iterdir()):
            if item.is_dir() and item.name in SKIP_DIRS:
                continue
            rel = str(item.relative_to(self.root)).replace("\\", "/")
            if item.is_dir():
                entries.append(f"  {rel}/")
            else:
                try:
                    size = item.stat().st_size
                    entries.append(f"  {rel}  ({size:,} bytes)")
                except OSError:
                    entries.append(f"  {rel}")
        if not entries:
            return f"Empty directory: {path}/"
        return f"Contents of {path}/:\n" + "\n".join(entries[:200])

    def _read_file(self, data: dict[str, Any]) -> str:
        path = data["path"]
        start = data.get("start_line")
        end = data.get("end_line")
        target = self._safe_path(path)

        if not target.is_file():
            return f"File not found: {path}"

        size = target.stat().st_size
        if size > 2 * 1024 * 1024:
            return f"File too large ({size:,} bytes). Use start_line/end_line to read a section."

        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return f"Cannot read: {exc}"

        lines = text.splitlines()
        total = len(lines)

        if start or end:
            s = max(1, start or 1) - 1
            e = min(total, end or total)
            selected = lines[s:e]
            start_num = s + 1
        else:
            if total > 500:
                selected = lines[:500]
                numbered = "\n".join(f"{i + 1:4d} | {ln}" for i, ln in enumerate(selected))
                return (
                    f"{path} ({total} lines, showing 1-500):\n{numbered}\n\n"
                    f"... [truncated — use start_line/end_line for more]"
                )
            selected = lines
            start_num = 1

        numbered = "\n".join(f"{start_num + i:4d} | {ln}" for i, ln in enumerate(selected))
        lo = start_num
        hi = start_num + len(selected) - 1 if selected else start_num
        return f"{path} (lines {lo}-{hi} of {total}):\n{numbered}"

    def _grep(self, data: dict[str, Any]) -> str:
        pattern_str = data["pattern"]
        path = data.get("path", ".")
        file_pattern = data.get("file_pattern")
        max_results = min(data.get("max_results", 50), 100)

        target = self._safe_path(path)
        if not target.exists():
            return f"Path not found: {path}"

        try:
            regex = re.compile(pattern_str, re.IGNORECASE)
        except re.error:
            regex = re.compile(re.escape(pattern_str), re.IGNORECASE)

        matches: list[str] = []
        files_searched = 0

        for root_dir, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for fname in files:
                if len(matches) >= max_results:
                    break
                fp = Path(root_dir) / fname
                if file_pattern and not fnmatch.fnmatch(fname, file_pattern):
                    continue
                try:
                    if fp.stat().st_size > 1024 * 1024:
                        continue
                    text = fp.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                files_searched += 1
                for line_num, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        rel = str(fp.relative_to(self.root)).replace("\\", "/")
                        matches.append(f"  {rel}:{line_num}: {line.rstrip()[:200]}")
                        if len(matches) >= max_results:
                            break

        if not matches:
            return f"No matches for '{pattern_str}' in {path}/ ({files_searched} files searched)"
        header = f"Found {len(matches)} match(es) for '{pattern_str}'"
        if len(matches) >= max_results:
            header += f" (capped at {max_results})"
        header += f" ({files_searched} files searched)"
        return header + ":\n" + "\n".join(matches)


# ─── Agentic loop ────────────────────────────────────────────────


async def run_subagent(
    client: AsyncClient,
    model: str,
    system_prompt: str,
    file_tree: str,
    repo_path: str,
    label: str,
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
) -> str:
    """Run a sub-agent with an autonomous tool-use loop.

    Claude navigates the repository by calling tools (list_files, read_file,
    grep), deciding on its own what to explore based on its analysis mandate.
    The loop continues until Claude produces a final text response or hits
    the tool call limit.
    """
    logger.info("Starting sub-agent: %s", label)
    executor = ToolExecutor(repo_path)

    user_message = (
        f"Here is the repository file tree:\n\n```\n{file_tree}\n```\n\n"
        f"Use the available tools to explore this repository. Read the files "
        f"you need, search for patterns, and build your analysis from actual "
        f"code evidence. Start by reading key files (README, entry points, "
        f"configs), then dig deeper based on what you find."
    )

    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]

    for turn in range(max_tool_calls):
        response = await client.messages.create(
            model=model,
            max_tokens=SUBAGENT_MAX_TOKENS,
            system=system_prompt,
            messages=messages,
            tools=REPO_TOOLS,
            temperature=0.0,
        )

        if response.stop_reason != "tool_use":
            result = ""
            for block in response.content:
                if block.type == "text":
                    result += block.text
            logger.info(
                "Sub-agent %s completed after %d turn(s) (%d chars)",
                label,
                turn + 1,
                len(result),
            )
            return result

        messages.append({"role": "assistant", "content": response.content})

        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "tool_use":
                logger.debug(
                    "  %s → %s(%s)",
                    label,
                    block.name,
                    json.dumps(block.input)[:120],
                )
                output = executor.execute(block.name, block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output,
                    }
                )

        messages.append({"role": "user", "content": tool_results})

    logger.warning(
        "Sub-agent %s hit tool call limit (%d). Requesting final answer.",
        label,
        max_tool_calls,
    )
    messages.append(
        {
            "role": "user",
            "content": (
                "You've reached the exploration limit. Produce your final "
                "analysis now based on everything you've read so far."
            ),
        }
    )
    response = await client.messages.create(
        model=model,
        max_tokens=SUBAGENT_MAX_TOKENS,
        system=system_prompt,
        messages=messages,
        temperature=0.0,
    )
    result = ""
    for block in response.content:
        if block.type == "text":
            result += block.text
    return result


# ─── Synthesis (forced structured output via tool_use) ───────────


async def _run_synthesis(
    client: AsyncClient,
    model: str,
    repo_name: str,
    repo_path: str,
    files_scanned: int,
    subagent_reports: dict[str, str],
    lang: str = "en",
) -> dict[str, Any]:
    """Merge all sub-agent reports into a structured RexReport.

    Uses tool_choice to force Claude to output valid JSON matching the schema.
    """
    logger.info("Starting synthesis agent")

    parts = [
        f"Repository: {repo_name}",
        f"Path: {repo_path}",
        f"Files scanned: {files_scanned}",
        "",
    ]
    for agent_name, report in subagent_reports.items():
        parts.append(f"## {agent_name} Report\n")
        parts.append(report)
        parts.append("")

    combined = "\n".join(parts)

    lang_name = LANG_NAMES.get(lang, "English")
    main_prompt = _load_prompt("main", lang_name=lang_name)
    synth_prompt = _load_prompt("synthesis", lang_name=lang_name)
    system = f"{main_prompt}\n\n{synth_prompt}"

    user_message = (
        f"Based on the following sub-agent analysis reports, produce the final "
        f"REX report as a JSON object matching the RexReport schema.\n\n"
        f"Important fields to fill:\n"
        f'- repo_name: "{repo_name}"\n'
        f'- repo_path: "{repo_path}"\n'
        f"- analyzed_at: current ISO timestamp\n"
        f'- model_used: "{model}"\n'
        f"- files_scanned: {files_scanned}\n\n"
        f"Sub-agent reports:\n\n{combined}\n\n"
        f"Output the complete RexReport as valid JSON. Use the exact field "
        f"names and enum values from the schema."
    )

    rex_report_schema = RexReport.model_json_schema()

    response = await client.messages.create(
        model=model,
        max_tokens=SYNTHESIS_MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user_message}],
        tools=[
            {
                "name": "produce_rex_report",
                "description": (
                    "Produce the final REX report. Call this tool with the "
                    "complete report data as a single JSON object."
                ),
                "input_schema": rex_report_schema,
            }
        ],
        tool_choice={"type": "tool", "name": "produce_rex_report"},
        temperature=0.0,
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "produce_rex_report":
            logger.info("Synthesis complete")
            return block.input  # type: ignore[return-value]

    raise RuntimeError("Synthesis agent did not produce a valid report")


# ─── Main pipeline ───────────────────────────────────────────────


async def run_analysis(
    repo_path: str,
    model: str = "claude-sonnet-4-6",
    api_key: str | None = None,
    provider: Provider = Provider.ANTHROPIC,
    foundry_resource: str | None = None,
    foundry_api_key: str | None = None,
    aws_region: str | None = None,
    gcp_project_id: str | None = None,
    gcp_region: str | None = None,
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    lang: str = "en",
) -> RexReport:
    """Run the full tribl analysis pipeline on a repository.

    1. Scan repo for file tree
    2. Run 4 sub-agents in parallel (each with autonomous tool-use loop)
    3. Synthesize findings into a structured RexReport
    """
    logger.info("Scanning repository: %s", repo_path)
    repo_map: RepoMap = scan_repo(repo_path)
    logger.info(
        "Found %d files (%d source files)",
        repo_map.total_files,
        len(repo_map.source_files),
    )

    if repo_map.total_files == 0:
        return RexReport(
            repo_name=_extract_repo_name(repo_path),
            repo_path=str(repo_path),
            analyzed_at=datetime.now(timezone.utc).isoformat(),
            model_used=model,
            files_scanned=0,
            repo_quality=RepoQuality.INSUFFICIENT,
            warnings=["Repository contains no scannable files."],
            rex_items=[],
            global_summary=("The repository is empty or contains only binary/ignored files."),
            strengths=[],
            improvement_suggestions=["Add source code to the repository."],
        )

    client = create_client(
        provider,
        api_key=api_key,
        foundry_resource=foundry_resource,
        foundry_api_key=foundry_api_key,
        aws_region=aws_region,
        gcp_project_id=gcp_project_id,
        gcp_region=gcp_region,
    )

    subagent_configs = [
        (_load_prompt("structure_analyzer"), "Structure Analyzer"),
        (_load_prompt("code_pattern_analyzer"), "Code Pattern Analyzer"),
        (_load_prompt("doc_analyzer"), "Documentation Analyzer"),
        (_load_prompt("config_analyzer"), "Configuration Analyzer"),
    ]

    results: list[str | None] = [None] * len(subagent_configs)

    lang_name = LANG_NAMES.get(lang, "English")

    async def _run_one(index: int, prompt: str, label: str) -> None:
        main = _load_prompt("main", lang_name=lang_name)
        system = f"{main}\n\n{prompt}"
        results[index] = await run_subagent(
            client,
            model,
            system,
            repo_map.file_tree,
            repo_path,
            label,
            max_tool_calls=max_tool_calls,
        )

    async with anyio.create_task_group() as tg:
        for i, (prompt, label) in enumerate(subagent_configs):
            tg.start_soon(_run_one, i, prompt, label)

    subagent_reports = {
        label: result for (_, label), result in zip(subagent_configs, results) if result
    }

    report_data = await _run_synthesis(
        client=client,
        model=model,
        repo_name=_extract_repo_name(repo_path),
        repo_path=str(repo_path),
        files_scanned=repo_map.total_files,
        subagent_reports=subagent_reports,
        lang=lang,
    )

    return RexReport.model_validate(report_data)


def _extract_repo_name(repo_path: str) -> str:
    """Extract a human-readable repo name from a path."""
    return Path(repo_path).resolve().name
