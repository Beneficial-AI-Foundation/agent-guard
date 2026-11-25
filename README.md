# AgentGuard

**Point your agents at AgentGuard instead of your tools.** AgentGuard is an MCP gateway between an AI agent and the GitHub MCP server. Every tool call passes through it, and a decision written in **Lean 4, with machine-checked proofs**, answers each one: **allow**, **ask a person**, or **deny**. Every decision is logged for audit.

However the agent is tricked (for example by prompt injection in a GitHub issue), the proved properties hold: a call matching a deny rule never runs; nothing read from a private repository is written to a public one; after reading outsider text, every high-impact action needs a person. [What exactly is proved](docs/proofs.md).

> **Status: research prototype.** The Lean core (13 theorems, no `sorry`), the gateway and the GitHub profile are built, and the six stories pass against real GitHub, scripted and with a real agent ([docs/testing.md](docs/testing.md)). Why it's built this way: [docs/design.md](docs/design.md).

## Try it on a test organisation

```bash
make proofs                              # build the Lean worker and check every proof
scripts/setup_test_repos.sh ORG          # demo-public and demo-private in a throwaway org
uv run agentguard init                   # ~/.agentguard/github; put a fine-grained token in its .env
make live OWNER=ORG                      # the six stories against real GitHub, through the gateway
uv run agentguard serve                  # then point an agent at http://127.0.0.1:8080/mcp
```

Step by step, including the token's permissions and the prompts to give an agent: [docs/testing.md](docs/testing.md).

| Command | What it does |
|---|---|
| `agentguard try "push_files owner=o repo=r branch=main"` | What the rules decide for one call, without an agent |
| `agentguard try` | Every tool on the server and what the rules say about it |
| `agentguard check` | Validate `rules.yaml` with Lean (also for CI) |
| `agentguard serve` / `stdio` | Run the gateway over HTTP (:8080/mcp) or stdio, with the console on :7070 |
| `agentguard report` | Summarise the audit log |
| `agentguard connect vscode` / `claude-code` / `cursor` | Point an agent's config at AgentGuard (stdio) and set aside its direct GitHub server |
| `agentguard doctor` | Check the worker, the rules, and that nothing goes around the gateway |
| `agentguard version` / `verify` | The worker build and its theorems / re-check the proofs from source |

## Layout

| Folder | What it holds |
|---|---|
| [`lean/`](lean/) | The proved decision: spec, matcher, proofs, the `guard-worker` binary. No MCP, YAML or GitHub. |
| [`src/`](src/) | The gateway, installed as the `agentguard` package. It moves bytes and never decides. |
| [`src/templates/github/`](src/templates/github/) | The GitHub profile: `mcp.json`, `rules.yaml`, `.env.example` |
| [`tests/`](tests/) | Unit, integration, property (Lean vs. reference, 10,000 cases), and `live/`: the six stories against real GitHub |
| [`site/`](site/) | The demo page: the stories with and without AgentGuard, run in the browser. Published to GitHub Pages by `.github/workflows/pages.yml` |
| [`docs/`](docs/) | [Rules](docs/rules.md) · [proofs](docs/proofs.md) · [threat model](docs/threat-model.md) · [architecture](docs/architecture.md) · [design](docs/design.md) · [testing](docs/testing.md) |

## Development

Needs [uv](https://docs.astral.sh/uv/) and [elan](https://github.com/leanprover/elan).

```bash
make check     # proofs + axiom check + ruff + mypy + tests (no credentials needed)
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the four rules that keep the design honest.
