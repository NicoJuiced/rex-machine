# rex-machine

**Your codebase has lessons no one wrote down. This finds them.**

rex-machine scans any code repository and extracts structured technical lessons learned — what problems the team faced, what they tried, what worked. Claude navigates your repo autonomously (reading files, grepping, following imports) and produces a grounded report, not a vague summary.

Works on any language, any framework, any repo size.

[PyPI](https://pypi.org/project/rex-machine/) ·
[GitHub](https://github.com/NicoJuiced/rex-machine)

## Install

```bash
pip install rex-machine
```

## Usage

```bash
# Set your API key (one time)
export ANTHROPIC_API_KEY=sk-ant-...

# Analyze a repo
rex extract /path/to/repo

# Save as Markdown
rex extract /path/to/repo -o markdown -f report.md

# Save as JSON
rex extract /path/to/repo -o json -f report.json

# Analyze in French
rex extract /path/to/repo --lang fr

# See what Claude is reading in real time
rex extract /path/to/repo -v
```

<!-- TODO: add demo video/gif here -->

## What you get

Each finding is structured, not prose:

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

Every REX has: a problem, approaches tried (what worked and what didn't), a learning, a confidence level grounded in code evidence, and the exact source files.

## Multi-provider

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

## How it works

Claude gets three read-only tools (`read_file`, `list_files`, `grep`) and decides what to explore on its own — same agentic loop as Claude Code. No files are pre-selected by heuristics. Claude reads what it needs, follows leads, and stops when it has enough evidence.

All tools are **read-only** and **sandboxed** to the repository. No writes, no network, no code execution.

Built with the raw [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python). No LangChain, no agent framework. The core loop is a `while stop_reason == "tool_use"` — [about 20 lines](src/rex_machine/agents.py).

## Configuration

```bash
rex init          # create .rex-machine.json in your project
rex configure     # set up provider & credentials
rex status        # show current config
```

## Contributing

[Issues](https://github.com/NicoJuiced/rex-machine/issues) and PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache 2.0](LICENSE)

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=NicoJuiced/rex-machine&type=Date)](https://star-history.com/#NicoJuiced/rex-machine&Date)
