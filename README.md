<div align="center">

# rex-machine

**The tribal knowledge your codebase never wrote down.**

[![PyPI version](https://img.shields.io/pypi/v/rex-machine?color=%2334D058&logo=pypi&logoColor=white)](https://pypi.org/project/rex-machine/)
[![Python](https://img.shields.io/pypi/pyversions/rex-machine?logo=python&logoColor=white)](https://pypi.org/project/rex-machine/)
[![CI](https://img.shields.io/github/actions/workflow/status/NicoJuiced/rex-machine/ci.yml?branch=main&logo=github&label=CI)](https://github.com/NicoJuiced/rex-machine/actions)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg?logo=opensourceinitiative&logoColor=white)](LICENSE)
[![Anthropic](https://img.shields.io/badge/Powered%20by-Claude-blueviolet?logo=data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cGF0aCBkPSJNMTIgMkM2LjQ4IDIgMiA2LjQ4IDIgMTJzNC40OCAxMCAxMCAxMCAxMC00LjQ4IDEwLTEwUzE3LjUyIDIgMTIgMnoiIGZpbGw9IiNmZmYiLz48L3N2Zz4=)](https://anthropic.com)

<br />

*rex-machine* lets **Claude navigate your repo like an engineer** — reading files, searching code, understanding structure — then extracts structured technical lessons learned (REX) grounded in real code evidence.

<br />

```
pip install rex-machine
```

<br />

</div>

---

## Demo

```
$ rex extract ./my-project

 rex-machine v0.1.0
 Analyzing: /home/dev/my-project
 Model: claude-sonnet-4-6
 Provider: anthropic

+---------------------- rex-machine Analysis Report ----------------------+
| my-project                                                              |
| Files scanned: 127                                                      |
| Repository Quality: Good                                                |
+-------------------------------------------------------------------------+

+---------------------------- Summary ------------------------------------+
| Well-structured FastAPI application with clear separation               |
| of concerns. Strong typing discipline throughout. Test                  |
| coverage focused on happy paths, edge cases under-tested.               |
+-------------------------------------------------------------------------+

 Strengths:
  + Consistent use of dependency injection via FastAPI Depends
  + Alembic migrations well-structured with rollback support
  + Comprehensive Pydantic schemas for all API boundaries

+-------------------------------------------------------------------------+
| REX #1: Error Handling Strategy              [Strongly Inferred]        |
+-------------------------------------------------------------------------+
  Context:   REST API with 23 endpoints
  Problem:   Inconsistent error responses across modules

  +---------------------+---------+--------------------------+
  | Approach            | Worked? | Details                  |
  +---------------------+---------+--------------------------+
  | Global exc handler  |   Yes   | Centralized in middleware|
  | Per-endpoint catch  |   No    | Led to code duplication  |
  +---------------------+---------+--------------------------+

  Learning:        Centralized error handling > scattered try/catch
  Recommendation:  Implement global exception middleware early
  Source files:    src/middleware/errors.py, src/api/deps.py

  ...
```

## Quick Start

```bash
# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# Analyze any repo
rex extract /path/to/repo

# Export as Markdown report
rex extract /path/to/repo -o markdown -f report.md

# Export as structured JSON
rex extract /path/to/repo -o json -f report.json

# Use a different model
rex extract /path/to/repo -m claude-opus-4-8

# Analyze in French
rex extract /path/to/repo --lang fr

# Use verbose mode to see tool calls
rex extract /path/to/repo -v
```

## How It Works

rex-machine works like **Claude Code analyzing your repo** — each AI agent autonomously navigates the codebase, reading files and searching code to build its analysis.

```
  Your Repo            rex-machine                     Claude API
 +----------+     +----------------+
 | source   |---->|  Scan file tree|
 | files    |     +-------+--------+
 | configs  |             |
 | docs     |             v
 +----------+     +------------------------------------------------+
       ^          |      4 Sub-agents (parallel via anyio)          |
       |          |                                                 |
       |          |  Structure --+  Patterns --+  Docs -+  Config -+|
       |          |              |             |        |          ||
       |          |              v             v        v          v|
       |          |        +----------------------------------+    |
       |<---------|--------|  Agentic tool-use loop            |    |
       | read_file|        |                                   |    |
       | grep     |        |  Claude decides what to read,     |    |
       | list     |        |  searches for patterns, follows   |    |
       |          |        |  imports, reads tests...          |    |
       |          |        |                                   |    |
       |          |        |  while stop_reason == "tool_use"  |    |
       |          |        +----------------------------------+    |
       |          +--------------------+---------------------------+
       |                               | 4 analysis reports
       |                               v
       |                       +---------------+
       |                       |  Synthesis    |
       |                       |  Agent        |--> Structured RexReport
       |                       | (tool_choice) |    (forced JSON schema)
       |                       +-------+-------+
       |                               |
       |                   +-----------+-----------+
       |                   v           v           v
       |                Console    Markdown      JSON
       |                (Rich)     (Jinja2)    (Pydantic)
       |
       +--- All tool calls are READ-ONLY and scoped to the repo
```

### The Agentic Loop

Each sub-agent receives the repository file tree as initial context, then **autonomously decides** what to explore:

1. **Claude reads the file tree** and picks what looks relevant to its analysis mandate
2. **Claude calls tools** — `read_file("src/auth/middleware.py")`, `grep("TODO|FIXME")`, `list_files("tests/")`
3. **rex-machine executes the tool** locally and returns the result
4. **Claude reads the result** and decides what to explore next
5. **Repeat** until Claude has enough evidence, or hits the tool call limit
6. **Claude produces its final analysis** as structured text

This is the same pattern Claude Code uses — a `while stop_reason == "tool_use"` loop where the model drives exploration.

### Available Tools

| Tool | Description | Example |
|------|-------------|---------|
| `list_files` | List directory contents or glob-match files | `list_files(path="src/", pattern="*.py")` |
| `read_file` | Read file contents with line numbers | `read_file(path="src/main.py", start_line=1, end_line=50)` |
| `grep` | Search for patterns across files | `grep(pattern="async def", file_pattern="*.py")` |

All tools are **read-only** and **scoped to the repository** — no path traversal, no writes, no network access.

### Sub-agents

| Sub-agent | Focus | What it typically reads |
|-----------|-------|----------------------|
| **Structure** | Directory layout, naming, module boundaries | README, build configs, directory listings |
| **Code Patterns** | Design patterns, anti-patterns, architectural choices | Source files, imports, error handling |
| **Documentation** | README quality, docstrings, ADRs, comments | Docs, README, source docstrings |
| **Configuration** | CI/CD, Docker, deps, linting, security | CI configs, Dockerfiles, linters, package manifests |

All four run **in parallel** via `anyio.create_task_group()` — the total analysis time is the time of the slowest agent, not the sum.

### Synthesis

The synthesis agent receives all four sub-agent reports and produces a unified `RexReport`. It uses **forced structured output** via `tool_choice` — Claude is required to call a tool whose `input_schema` is the Pydantic-generated JSON Schema of `RexReport`. This guarantees valid, schema-compliant JSON without any parsing hacks.

## Architecture Deep Dive

### Why an Agentic Loop (vs Static File Dump)

The first version pre-scanned the repo with Python, assigned static priority scores to files, read the top-N files within a character budget, and sent the entire blob to Claude. This had fundamental limitations:

- **Claude couldn't ask for more** — if the priority scoring missed a key file, Claude would never see it
- **Wasted tokens** — many pre-read files were irrelevant to a specific sub-agent's focus
- **No cross-referencing** — Claude couldn't follow an import to understand a dependency
- **Rigid heuristics** — a `README.md` always ranked higher than source code, even when the README was empty

The agentic approach fixes all of these. Claude reads what *it* needs, follows leads, and stops when it has enough evidence. A structure analyst reads different files than a code pattern analyst — and that's exactly what happens now.

### Why 4 Specialized Sub-agents (vs 1 General Agent)

A single agent analyzing everything would produce shallow, generic findings. Specialization forces depth:

- Each sub-agent has a **focused mandate** (structure, patterns, docs, config) with a tailored system prompt
- They run in **parallel** — 4x faster than sequential
- The synthesis step **cross-references** and **deduplicates** findings, catching things a single pass would miss
- Each agent explores different parts of the repo, giving **broader coverage** without a massive context window

### Why the `anthropic` SDK Directly

rex-machine uses the [official Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) (`anthropic`) — not LangChain, CrewAI, AutoGen, or any agent framework. Why:

- **Zero abstraction tax** — the SDK's `messages.create()` is the only API surface needed. A `while stop_reason == "tool_use"` loop is ~20 lines of code. Frameworks add layers without adding value here.
- **Full control over the agentic loop** — tool execution, message threading, error handling, and safety caps are all explicit Python code you can read and debug.
- **Multi-provider support** — the SDK natively supports Anthropic direct, Azure AI Foundry, AWS Bedrock, and Google Vertex AI via `AsyncAnthropic`, `AsyncAnthropicBedrock`, `AsyncAnthropicVertex`. One `create_client()` factory, zero third-party adapters.
- **No dependency risk** — the Anthropic SDK is the most stable dependency in the Claude ecosystem. Agent frameworks have fast-moving APIs and frequent breaking changes.

### Why `tool_use` + `tool_choice` for Structured Output

The synthesis agent must output a valid `RexReport` JSON object. rex-machine forces this via the `tool_use` pattern:

```python
response = await client.messages.create(
    # ...
    tools=[{
        "name": "produce_rex_report",
        "input_schema": RexReport.model_json_schema(),  # Pydantic -> JSON Schema
    }],
    tool_choice={"type": "tool", "name": "produce_rex_report"},
)
# Claude MUST call this tool -> input is guaranteed to match the schema
report_data = response.content[0].input
```

This is more reliable than asking Claude to output JSON in a text block because:
- The API **validates the JSON against the schema** before returning
- No parsing, no regex extraction, no "please don't wrap in code fences"
- The schema is auto-generated from Pydantic models — single source of truth

### Why `anyio` for Concurrency

rex-machine uses `anyio` (not raw `asyncio`) for parallel sub-agent execution:

```python
async with anyio.create_task_group() as tg:
    for i, (prompt, label) in enumerate(subagent_configs):
        tg.start_soon(_run_one, i, prompt, label)
```

- **Backend-agnostic** — works on both `asyncio` and `trio`
- **Structured concurrency** — if any sub-agent crashes, the entire group is cancelled cleanly (no orphan tasks)
- **Idiomatic for Anthropic** — the SDK uses `httpx` which is anyio-native

### Why Pydantic v2

Every rex-machine report is a `RexReport` Pydantic model:

- **Schema generation** — `RexReport.model_json_schema()` produces the exact JSON Schema used by the `tool_use` pattern, ensuring Claude's output matches the Python types
- **Validation** — `RexReport.model_validate(data)` catches malformed reports before rendering
- **Serialization** — `.model_dump_json()` for JSON export, direct attribute access for console/markdown rendering

### Why Jinja2 for Prompts

System prompts are stored as `.j2` template files, not Python string literals:

```
src/rex_machine/templates/prompts/
  main.j2
  structure_analyzer.j2
  code_pattern_analyzer.j2
  doc_analyzer.j2
  config_analyzer.j2
  synthesis.j2
```

- **Separation of concerns** — prompt engineering and Python code are decoupled
- **Readable** — prompts are plain text files, not f-strings buried in code
- **Extensible** — Jinja2 supports variables, conditionals, loops for future prompt parameterization
- **Diffable** — prompt changes show up cleanly in git diffs

## REX Structure

Every extracted lesson follows the **tripartite structure**:

```
Problem        ->  What was the challenge?
Approaches     ->  What was tried? What worked, what didn't?
Learnings      ->  What's the takeaway?
```

Each REX includes a **confidence level** based on code evidence:

| Level | Meaning |
|-------|---------|
| `strongly_inferred` | Strong direct evidence in the code |
| `probable` | Good evidence with minor inference |
| `cautious_hypothesis` | Some evidence, significant inference |
| `insufficient_signal` | Weak signal — flagged as low-confidence |

## Output Formats

| Format | Flag | Best for |
|--------|------|----------|
| **Console** | `-o console` | Interactive exploration (default) |
| **Markdown** | `-o markdown` | Wiki pages, PR descriptions, docs |
| **JSON** | `-o json` | CI pipelines, dashboards, further processing |

## Configuration

rex-machine uses a **two-level config** system:

| Level | File | Contains | Commitable? |
|-------|------|----------|-------------|
| **Global** | `~/.config/rex-machine/config.json` | API keys, provider | No (secrets) |
| **Project** | `.rex-machine.json` in repo root | Model, output format, options | Yes |

```bash
# Set up credentials (saved globally)
rex configure

# Create project config
rex init

# View current configuration
rex status
```

### Project Config (`.rex-machine.json`)

> **Never put API keys or secrets in this file** — it's meant to be committed to your repo. Secrets belong in env vars or `~/.config/rex-machine/config.json`.

```json
{
  "model": "claude-sonnet-4-6",
  "output": "console",
  "max_tool_calls": 30
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `model` | `claude-sonnet-4-6` | Claude model to use |
| `output` | `console` | Default output format |
| `max_tool_calls` | `30` | Max tool calls per sub-agent (safety cap) |

### Multi-Provider Support

| Provider | Flag | Auth |
|----------|------|------|
| **Anthropic** | `--provider anthropic` | `ANTHROPIC_API_KEY` |
| **Azure AI Foundry** | `--provider foundry` | `ANTHROPIC_FOUNDRY_RESOURCE` + `ANTHROPIC_FOUNDRY_API_KEY` |
| **AWS Bedrock** | `--provider bedrock` | AWS credentials (`~/.aws/credentials` or env vars) |
| **Google Vertex AI** | `--provider vertex` | GCP credentials (`gcloud auth` or env vars) |

## Design Principles

| Principle | What it means |
|-----------|---------------|
| **Agentic** | Claude navigates the repo autonomously, like Claude Code |
| **Read-only** | rex-machine never modifies the analyzed repository |
| **Anti-hallucination** | Every REX must be grounded in code Claude actually read |
| **Conservative** | Fewer high-quality REX beats many weak ones |
| **Transparent** | Confidence levels + source file references on every finding |

## Development

```bash
# Clone & install
git clone https://github.com/NicoJuiced/rex-machine.git
cd rex-machine
pip install -e ".[dev]"

# Test
pytest

# Lint
ruff check src/ tests/
ruff format src/ tests/
```

## Publishing to PyPI

```bash
# Tag a release (CI auto-publishes)
git tag v0.1.0
git push --tags
```

> Set up [PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/) for your GitHub repo first.

## License

[Apache 2.0](LICENSE)

---

<div align="center">

Built with [Claude](https://anthropic.com) by [@NicoJuiced](https://github.com/NicolasJULIEN)

**rex-machine** — *because the best lessons are already in your code.*

</div>
