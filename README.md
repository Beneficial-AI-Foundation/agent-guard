# AgentGuard

**Point your agents at AgentGuard instead of your tools.** AgentGuard is an MCP gateway between an AI agent and the GitHub MCP server. Every tool call passes through it, and a decision written in **Lean 4, with machine-checked proofs**, answers each one: **allow**, **ask a person**, or **deny**. Every decision is logged for audit.

However the agent is tricked (for example by prompt injection in a GitHub issue), the proved properties hold: a call matching a deny rule never runs; nothing read from a private repository is written to a public one; after reading outsider text, every high-impact action needs a person. [What exactly is proved](docs/proofs.md).

> **Status: research prototype.** Phases 0–3 of 5 are built: the Lean core (10 theorems, no `sorry`), the gateway, the GitHub profile and an offline demo. Not yet run against the live GitHub MCP server with a real agent (phase 4). See [docs/session-history.md](docs/session-history.md).

## See it work (offline, 1 minute)

```bash
make proofs            # build the Lean worker and check every proof
uv run agentguard demo # six GitHub stories against a mock server, through the real gateway
```

Or in Docker (no Lean or Python needed): `docker compose run --rm demo`.

## Use it with your agent

```bash
agentguard init github          # ~/.agentguard/github: mcp.json, rules.yaml, .env; signs in to GitHub
agentguard connect vscode       # or claude-code, cursor: adds AgentGuard, sets aside the direct GitHub server
agentguard doctor               # checks nothing can go around the gateway
```

Then open the console link AgentGuard prints (or run `agentguard serve`) to watch calls and answer "ask" prompts. Details: [docs/quickstart.md](docs/quickstart.md).

| Command | What it does |
|---|---|
| `agentguard try "push_files owner=o repo=r branch=main"` | What the rules decide for one call, without an agent |
| `agentguard try` | Every tool on the server and what the rules say about it |
| `agentguard check` | Validate `rules.yaml` with Lean (also for CI) |
| `agentguard serve` / `stdio` | Run the gateway over HTTP (:8080/mcp) or stdio, with the console on :7070 |
| `agentguard report` | Summarise the audit log |
| `agentguard version` / `verify` | The worker build and its theorems / re-check the proofs from source |

## Layout

| Folder | What it holds |
|---|---|
| [`lean/`](lean/) | The proved decision: spec, matcher, proofs, the `guard-worker` binary. No MCP, YAML or GitHub. |
| [`src/`](src/) | The gateway, installed as the `agentguard` package. It moves bytes and never decides. |
| [`src/templates/github/`](src/templates/github/) | The GitHub profile: `mcp.json`, `rules.yaml`, the mock server and demo stories |
| [`tests/`](tests/), [`examples/`](examples/) | Unit, integration, property (Lean vs. reference, 10,000 cases) and story tests |
| [`docs/`](docs/) | [Rules](docs/rules.md) · [proofs](docs/proofs.md) · [threat model](docs/threat-model.md) · [architecture](docs/architecture.md) · [testing](docs/testing.md) |

## Development

Needs [uv](https://docs.astral.sh/uv/) and [elan](https://github.com/leanprover/elan).

```bash
make check     # proofs + axiom check + ruff + mypy + all tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the four rules that keep the design honest.
