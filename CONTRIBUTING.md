# Contributing

## Four rules that keep AgentGuard clean

1. **Every verdict comes from `lean/`.** Nothing in `src/` decides allow, ask or deny. A missing answer or an error from Lean means deny.
2. **A change to the rule language starts in `lean/Guard/Spec/`.** `Impl/`, `Proofs/`, `src/monitor/reference.py`, the schema and `docs/rules.md` change in the same PR.
3. **GitHub appears only in `src/templates/github/`, `examples/github/` and `tests/live/`.**
4. **A new connection is a new template and example folder**, not new gateway code.

## Before you open a PR

```bash
make check     # proofs + axiom check + ruff + mypy + pytest
```

CI runs the same checks and blocks the merge if any fail. `lake build --wfail` treats Lean warnings as errors, and `check-axioms` rejects `sorry`, `native_decide` and any axiom other than `propext`, `Classical.choice` and `Quot.sound`.

## Layout notes

- `src/` **is** the `agentguard` package (setuptools `package-dir`). There is no `src/agentguard/` folder; code inside uses relative imports.
- Each new Python subpackage must be added to `[tool.setuptools] packages` in `pyproject.toml`. A test fails if one is missing.
- Static tools (mypy, Pylance/pyright) resolve `agentguard` through the `.typing/agentguard → ../src` symlink, because they can't follow setuptools' editable import hook.
- Lean module files are UpperCamelCase (`Guard/Spec/Rules.lean`), following Lean convention. Python stays lowercase.
- Lean 4 without Mathlib. Glob matching and argument lookup are written and proved by hand.
