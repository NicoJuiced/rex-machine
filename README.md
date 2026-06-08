# rex-machine

**Your codebase has lessons no one wrote down. This finds them.**

rex-machine scans any code repository and extracts structured technical lessons learned — what problems the team faced, what they tried, what worked. Claude navigates your repo autonomously (reading files, grepping, following imports) and produces a grounded report, not a vague summary.

Works on any language, any framework, any repo size.

[PyPI](https://pypi.org/project/rex-machine/) ·
[GitHub](https://github.com/NicoJuiced/rex-machine)

## 1. Quick start

```bash
pip install rex-machine
export ANTHROPIC_API_KEY=sk-ant-...
rex extract /path/to/repo
```

<!-- TODO: add demo video/gif here -->

## 2. Export reports

Get the results in the format you need.

```bash
# Markdown — for wikis, PRs, documentation
rex extract /path/to/repo -o markdown -f report.md

# JSON — for CI pipelines, dashboards, automation
rex extract /path/to/repo -o json -f report.json

# French output
rex extract /path/to/repo --lang fr
```

## 3. Multi-provider

Works with any Claude provider. Auto-detects from environment variables.

| Provider | Auth |
|----------|------|
| Anthropic (default) | `ANTHROPIC_API_KEY` |
| Azure AI Foundry | `ANTHROPIC_FOUNDRY_RESOURCE` + `ANTHROPIC_FOUNDRY_API_KEY` |
| AWS Bedrock | AWS credentials |
| Google Vertex AI | GCP credentials |

```bash
rex configure  # interactive setup
```

## 4. What you get

Each finding is structured, not prose:

- **Problem** — what was the challenge
- **Approaches** — what was tried, what worked, what didn't
- **Learning** — the takeaway
- **Confidence** — how strong the code evidence is
- **Source files** — exactly where Claude found it

```
REX #1: Error Handling Strategy                    [Strongly Inferred]

  Context:    REST API with 23 endpoints
  Problem:    Inconsistent error responses across modules

  Approach             Worked?   Details
  Global exc handler   Yes       Centralized in middleware
  Per-endpoint catch   No        Led to code duplication

  Learning:        Centralized error handling > scattered try/catch
  Recommendation:  Implement global exception middleware early
  Source files:    src/middleware/errors.py, src/api/deps.py
```

## How it works

Claude gets three read-only tools (`read_file`, `list_files`, `grep`) and decides what to explore on its own — same agentic loop as Claude Code. No files are pre-selected by heuristics. Claude reads what it needs, follows leads, and stops when it has enough evidence.

All tools are **read-only** and **sandboxed** to the repository. No writes, no network, no code execution.

Built with the raw [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python). No LangChain, no agent framework. The core loop is a `while stop_reason == "tool_use"` — [about 20 lines](src/rex_machine/agents.py).

## Configuration

```bash
rex init          # create .rex-machine.json in your project
rex configure     # set up provider & credentials (saved in ~/.config/rex-machine/)
rex status        # show current config
```

Project config (`.rex-machine.json`) is safe to commit — no secrets.

## Contributing

[Issues](https://github.com/NicoJuiced/rex-machine/issues) and PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
git clone https://github.com/NicoJuiced/rex-machine.git
cd rex-machine
pip install -e ".[dev]"
pytest
```

## License

[Apache 2.0](LICENSE)
