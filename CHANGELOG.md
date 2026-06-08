# Changelog

## 0.1.0 (Unreleased)

Initial release.

- Agentic analysis pipeline with 4 parallel sub-agents (structure, patterns, docs, config)
- Each sub-agent autonomously navigates the repo via `read_file`, `list_files`, `grep`
- Synthesis agent merges findings into a structured `RexReport` via forced `tool_use`
- Output formats: Rich console, Markdown (Jinja2), JSON
- Multi-provider support: Anthropic direct, Azure AI Foundry, AWS Bedrock, Google Vertex AI
- Two-level configuration (global credentials + per-project settings)
- `.gitignore`-aware file scanner with binary detection
- Safety cap on tool calls per sub-agent (default 30)
- French and English output (`--lang fr`)
