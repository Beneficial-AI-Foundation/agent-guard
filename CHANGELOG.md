# Changelog

## Unreleased

- **Frontier-risk template.** 33 rules from the FLI AI Safety Index (Summer 2026) and AIR-Bench 2024 about what an agent may do (no network scanning, no operating weapons, nuclear or other critical systems, a person for sends and automated decisions about people), as `docs/frontier-risk-rules.yaml`. Lean proves that the template keeps deciding the calls it catches whatever rules follow it (`lean/Guard/Rulesets/FrontierRisk.lean`). `docs/frontier-risk.md` maps all 40 agent-action rules from the Index and its benchmarks to these rules or to existing theorems. No change to the rule language.

## 0.0.1 (unreleased)

First version: an MCP gateway for the GitHub MCP server whose allow / ask / deny decisions are proved in Lean 4.

- **Lean core.** Spec (glob, rules, semantics, sessions); a derivative-based glob matcher proved equal to the spec; ten safety theorems proved over whole runs (no `sorry`, standard axioms only); a JSON-lines `guard-worker` with strict rule-file validation; `#guard` examples for the six stories.
- **Gateway.** Profiles in VS Code / Claude Code / Cursor `mcp.json` style with `.env`; the Lean worker client (errors mean deny); an independent Python reference checked against Lean on 10,000 random cases; MCP proxy over stdio and HTTP for protocol versions 2025-11-25 and 2026-07-28; approvals; audit log; `enforce` / `audit` / `off` modes; a local console.
- **Credentials.** The upstream server's token comes from the profile's `.env` and is sent as a header, as in VS Code; the agent never sees it.
- **GitHub profile.** `mcp.json`, 31 rules and `.env.example`, with tool names checked against GitHub's remote MCP server.
- **Commands.** `init`, `connect` (VS Code, Claude Code, Cursor), `doctor`, `try`, `check`, `serve`, `stdio`, `report`, `verify`, `version`.
- **Testing.** `make check` (proofs, axioms, lint, types, tests; no credentials) and `make live OWNER=…`: the six stories against a real test organisation. Checked end to end with a real agent ([docs/testing.md](docs/testing.md)).
- **Demo page.** `site/index.html`: the stories with and without AgentGuard, run in the browser; published to GitHub Pages on every change to `site/`.
