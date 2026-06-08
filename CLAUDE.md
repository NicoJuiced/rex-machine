# tribl

A Python CLI tool that extracts technical lessons learned (REX - Retours d'EXperience) from code repositories using the Claude API.

## Architecture

**Agentic tool-use pipeline** — each sub-agent navigates the repo autonomously via tool calls (like Claude Code):

1. **Scanner** (`src/tribl/scanner.py`) - Walks the local repo, respects .gitignore, skips binaries, builds a file tree map.
2. **Sub-agents** (`src/tribl/agents.py`) - Four parallel Claude API calls, each with an autonomous `while stop_reason == "tool_use"` loop. Claude calls `list_files`, `read_file`, `grep` to explore the codebase and decides what to read based on what it finds.
3. **Synthesis** (`src/tribl/agents.py`) - A final Claude API call merges all sub-agent findings into a structured `RexReport` using tool_use for structured JSON output.
4. **Renderer** (`src/tribl/renderer.py`) - Outputs the report as Rich console, Markdown (via Jinja2), or JSON.

## Key Design Decisions

- Uses the official `anthropic` Python SDK (not any agent framework).
- Sub-agents navigate the repo via read-only tools (`list_files`, `read_file`, `grep`) — all scoped to the repo directory, no path traversal.
- Structured output is enforced via the `tool_use` / `tool_choice` pattern (not `response_format`).
- Parallel sub-agent execution uses `anyio` task groups.
- Default model: `claude-sonnet-4-6` (cost-effective for analysis).
- Safety cap: `max_tool_calls` per sub-agent (default 30) prevents runaway loops.

## Commands

```bash
# Install in dev mode
pip install -e ".[dev]"

# Run analysis
tribl analyze /path/to/repo
tribl analyze /path/to/repo -o markdown -f report.md
tribl analyze /path/to/repo -o json -f report.json
tribl analyze /path/to/repo -m claude-sonnet-4-6 -v

# Run tests
pytest

# Lint
ruff check src/ tests/
ruff format src/ tests/
```

## Environment Variables

- `ANTHROPIC_API_KEY` - Required. Your Anthropic API key.

## Project Layout

```
src/tribl/
  __init__.py       - Package version
  models.py         - Pydantic v2 models (RexReport, RexItem, etc.)
  scanner.py        - Local repo file scanner (builds file tree, SKIP_DIRS)
  agents.py         - Agentic pipeline (tool-use loop, ToolExecutor, synthesis)
  renderer.py       - Output renderers (console, markdown, json)
  config.py         - Two-level config management (global + project)
  cli.py            - Typer CLI entry point
  templates/
    prompts/        - Jinja2 prompt templates for each agent
    report.md.j2    - Jinja2 markdown report template
tests/
  test_models.py    - Model validation tests
  test_scanner.py   - Scanner and ToolExecutor tests
```
