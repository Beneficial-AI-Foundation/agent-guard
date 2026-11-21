# Notes for coding agents

AgentGuard is an MCP gateway: agent → AgentGuard → GitHub MCP server. A Lean 4 decision with machine-checked proofs answers every tool call with allow, ask or deny. Full design and plan: `docs/session-history.md`.

## Rules (also in CONTRIBUTING.md)

1. Every verdict comes from `lean/`. Nothing in `src/` decides allow / ask / deny. Errors from Lean mean deny.
2. Rule-language changes start in `lean/Guard/Spec/`; Impl, Proofs, `src/monitor/reference.py`, the schema and `docs/rules.md` change in the same PR.
3. GitHub appears only in `src/templates/github/`, `examples/github/`, `tests/live/`.
4. A new connection is a new template and example folder, not new gateway code.

## Proofs

- `lean/Guard/Spec/` is the meaning; `Spec/Safety.lean` holds the theorem statements as `Prop`s; `Proofs/` proves them.
- Only glob matching has a separate implementation (`Impl/Glob.lean`, proved equal in `Proofs/Glob.lean`, which also supplies the `Decidable` instance). The worker runs `Guard.step` from the spec itself.
- Spec changes: update the statements first and get them reviewed by a person before proving.
- `lean/GuardTest/` holds `#guard` examples (glob cases, the demo stories); they fail the build if false.
- Never commit `sorry`, `admit`, `native_decide` or new `axiom`s. `scripts/check_proofs.sh` must pass.
- No Mathlib.

## Commands

- `make check`: everything CI runs.
- `scripts/check_proofs.sh`: Lean build (warnings are errors) + axiom check.
- `uv run pytest`, `uv run ruff check .`, `uv run mypy -p agentguard && uv run mypy tests`.

## Packaging gotchas

- `src/` is installed as `agentguard` via setuptools `package-dir`; there is no `src/agentguard/`. Use relative imports inside `src/`.
- New subpackage → add it to `[tool.setuptools] packages` (a test checks this).
- mypy/pyright see the package through the `.typing/agentguard` symlink.

## Layout notes

- The GitHub profile, its mock server and the demo stories live in `src/templates/github/` (so they ship in the wheel); `examples/github/` has its README and story tests.
- `src/demo.py` runs any template's stories; it holds no GitHub knowledge.
- `src/monitor/reference.py` is for tests (and the display in `agentguard try`); it never decides a real call.
- A "direct" server in an agent's config is one with the same URL or command as a guarded server (`src/clients/base.py`).

## Workflow

- Commit after each step and push. Never commit `.env`, tokens or `audit.jsonl`.
- Secrets are never logged.
