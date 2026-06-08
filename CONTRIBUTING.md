# Contributing to rex-machine

Thanks for your interest! Here's how to get started.

## Setup

```bash
git clone https://github.com/NicolasJULIEN/rex-machine.git
cd rex-machine
pip install -e ".[dev]"
```

## Development workflow

```bash
# Run tests
pytest

# Lint + format
ruff check src/ tests/
ruff format src/ tests/
```

All checks must pass before merging. CI runs them automatically on every PR.

## Pull requests

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Add or update tests if applicable
4. Ensure `pytest` and `ruff check` pass
5. Open a PR with a clear description of *what* and *why*

## Architecture overview

See [CLAUDE.md](CLAUDE.md) for the full architecture and design decisions.

The key thing to understand: rex-machine uses an **agentic tool-use loop** where Claude autonomously navigates the repo via `read_file`, `list_files`, and `grep` tools. If you're adding a new tool or sub-agent, follow the existing patterns in `src/rex_machine/agents.py`.

## Reporting bugs

Use [GitHub Issues](https://github.com/NicolasJULIEN/rex-machine/issues) with the bug report template. Include `rex extract --verbose` output when possible.
