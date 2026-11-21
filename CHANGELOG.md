# Changelog

## Unreleased

- Phase 4 prep: template tool names checked against github-mcp-server v2.2.0 (workflow tools renamed to `actions_list`, `actions_get`, `actions_run_trigger`; `issue_write` now high impact); `scripts/phase4_preflight.py`; headless-agent prompt tests; `docs/phase4.md` runbook.

- Phase 3: GitHub profile. Template (`mcp.json`, 35 rules, `.env.example`), offline mock GitHub MCP server, six stories, and the `init`, `try`, `demo`, `report`, `connect` (VS Code, Claude Code, Cursor) and `doctor` commands.
- Phase 2: gateway. Profile loading (VS Code and Claude/Cursor `mcp.json`, `.env`), Lean worker client (errors are deny), Python reference and 10,000-case property test, MCP proxy over stdio and HTTP, approvals, audit log, modes, console, GitHub device flow and MCP OAuth sign-in.

- Phase 1: Lean core. Spec (glob, rules, semantics, sessions), derivative-based glob matcher proved equal to the spec, ten safety theorems proved (no `sorry`, standard axioms only), JSON-lines `guard-worker` with strict rule-file validation, `#guard` story tests, docs (rules, proofs, threat model), JSON schema.

- Phase 0: repository setup, CI, `src/` → `agentguard` packaging, Lean project skeleton with axiom check.
