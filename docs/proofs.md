# What is proved

Every verdict AgentGuard gives (allow, ask or deny) is computed by Lean code whose properties are machine-checked. This page lists those properties, how the proof is organised, and how to check it yourself.

## The theorems

All of them hold for **every** rule file, **every** sequence of tool calls, **every** starting session, and **every** person answering the `ask` prompts, even one who approves everything. So they hold however the agent is tricked into choosing its calls.

`kill_switch` and `stopped_sticky` are **proved, but not yet reachable from a rule file**: nothing sets `Session.stopped` yet, so no profile can trigger them. The console control lands separately.
The last six are about the `servers` block: how a connection names the thing a call touches, and which of its tools have each capability. See [rules.md](rules.md#servers-resources-and-capabilities).

| Theorem | In plain words |
|---|---|
| `impl_eq_spec` | The glob matcher that runs gives exactly the spec's answer. Everything else runs the spec's own definitions. |
| `executed_only_if_allowed` | A call runs only if it was allowed, or asked and approved. |
| `unmatched_denied` | A call that matches no rule never runs. |
| `deny_rule_always_denies` | If the first matching rule says deny, the call never runs. |
| `ask_rule_needs_person` | If the first matching rule says ask, the call is never allowed, and runs only if the person approves. |
| `allow_needs_allow_rule` | Only an allow rule can allow. |
| `no_exfiltration` | Every call that isn't denied writes only to labels at least as high as everything read before it by calls that ran. After reading the private repo, nothing is written to a public one. |
| `level_monotone` | The session level never goes down, so rewording data doesn't launder it. |
| `no_untrusted_steering` | After outsider text has been read, no high-impact call is allowed without a person. |
| `approval_cannot_leak` | A call shown to a person is already within the leak rules, so approving it can't leak. |
| `kill_switch` | Once a person has stopped the session, no later call runs, whatever the rules say and whoever answers `ask`. |
| `stopped_sticky` | A stopped session stays stopped: nothing `step` does clears the flag. |
| `unlisted_server_names_nothing` | A server the policy doesn't list names no resource, so nothing is assumed about an undeclared connection. |
| `flat_server_label` | A server declared `flat l` reads and writes at label `l`, whatever the call's arguments say. |
| `unknown_resource_is_safe` | A resource the policy can't name is read as the highest label and written as the lowest, so it can't launder data. |
| `capability_needs_declaration` | A rule selected by capability never reaches a tool whose connection didn't declare that capability. |
| `unlisted_server_has_no_caps` | A server the policy doesn't list has no capabilities, so no capability rule fires for it. |
| `name_rules_unchanged` | A rule with no capability applies exactly on its tool pattern and conditions, as every rule does today. |

The exact statements are in [`lean/Guard/Spec/Safety.lean`](../lean/Guard/Spec/Safety.lean), and the proofs are in [`lean/Guard/Proofs/`](../lean/Guard/Proofs/).

## Rule templates

Some theorems are about a particular list of rules rather than every rule file. The **frontier-risk template** ([frontier-risk.md](frontier-risk.md)) covers 33 rules from the FLI AI Safety Index and AIR-Bench 2024. Placed at the top of a rule file, it is proved to keep deciding the calls it catches whatever rules follow it: deny rules always deny (`template_deny_never_runs`), and nothing it catches runs without a person (`template_needs_person`). The proofs are in [`lean/Guard/Rulesets/FrontierRisk.lean`](../lean/Guard/Rulesets/FrontierRisk.lean) and are checked by `check-axioms` like the rest of `Guard.*`.

## How it is organised

```
lean/Guard/
├── Spec/      what reviewers read
│   ├── Glob.lean        what a pattern matches (inference rules)
│   ├── Rules.lean       tool calls, rules, policies
│   ├── Semantics.lean   conditions, first match wins, no match = deny
│   ├── Session.lean     repository labels, classification, the decision, a whole session
│   └── Safety.lean      the theorem statements
├── Impl/Glob.lean       the matcher that runs (pattern derivatives, no backtracking)
├── Proofs/
│   ├── Glob.lean        Impl.glob agrees with Spec's Glob
│   └── Safety.lean      proofs of every statement in Spec/Safety.lean
├── Wire/                JSON in and out, rule-file validation (trusted, not proved)
└── Rulesets/            ready-made rule lists and what they guarantee (FrontierRisk)
```

Two layers keep the proofs from being circular:

1. **Spec**: short definitions of what rules mean. To trust AgentGuard you need to read these, not the proofs.
2. **Proofs**: (a) the code that runs equals the spec, and (b) the spec has the safety properties.

The only part of the decision with a separate implementation is glob matching. The spec defines it with inference rules (`Matches`), and the matcher that runs simulates the pattern as an automaton using pattern derivatives. `glob_correct` proves the two agree, and that proof provides the `Decidable` instance the rest of the spec uses. So the worker runs `Guard.step` from the spec itself, and nothing else needs an `Impl = Spec` proof.

## What a reviewer should check

The proofs only guarantee what the statements say. A reviewer should read `Spec/` and ask:

- Do the definitions say what the rule language should mean? ([docs/rules.md](rules.md) is the same thing in words.)
- Are the statements in `Spec/Safety.lean` the properties we want, without hidden assumptions?

Changes under `lean/Guard/Spec/` need a second reviewer (see `.github/CODEOWNERS`).

## Checking it yourself

```bash
scripts/check_proofs.sh
```

This builds the Lean code with warnings treated as errors, builds the `#guard` examples in `lean/GuardTest/`, and runs `check-axioms`. That checker loads every declaration in `Guard.*` and fails if any of them depends on `sorry`, `native_decide` or an axiom other than Lean's standard three (`propext`, `Classical.choice`, `Quot.sound`).

`guard-worker --info` lists the theorems that the binary you are running was built with.

## What is not proved

See [threat-model.md](threat-model.md): the Lean kernel and compiler, the JSON layer, the Python gateway, the MCP SDK, GitHub, and whether your rule file and labels describe reality.
