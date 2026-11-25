# The frontier-risk template

The [FLI AI Safety Index](https://futureoflife.org/index) (Summer 2026) and the four benchmarks it uses (AIR-Bench 2024, HELM Safety v1.0, TrustLLM, CAIS AI Dashboard) contain 388 safety rules in total. **40 of them are about what an agent is allowed to do**, so AgentGuard can enforce them and Lean can prove they hold. This page lists all 40 and says what covers each one.

- **33 items** are new, and become **20 rules**: the template in [`frontier-risk-rules.yaml`](frontier-risk-rules.yaml), proved in [`lean/Guard/Rulesets/FrontierRisk.lean`](../lean/Guard/Rulesets/FrontierRisk.lean). Fewer rules than items because several items are the same thing done by different means — spoofing and packet forgery are one rule, and the ten critical-system items are one.
- **5 items** were already covered by AgentGuard's existing theorems.
- **2 items** needed a change to the rule language. One is now done ([R021, the kill switch](proofs.md)); the other (budgets) is still a proposal.

The rule wording and the choice of which items fit are BAIF's interpretation (Nov 2026), not FLI's or the benchmark authors'. AIR-Bench rules read "refuse requests that facilitate …"; AgentGuard enforces only the **agent-action** part (the agent can't *do* it). Whether a model's text helps someone do it is outside AgentGuard.

## How to use the template

**Every rule selects on a capability, not on a tool name.** So the template says nothing about what your tools are called. It catches exactly the tools a connection declared, in its own `servers:` block, as scanning a network or sending a message or operating a physical system.

1. Declare your connections' capabilities (see [rules.md](rules.md#servers-resources-and-capabilities)):

   ```yaml
   servers:
     - name: github
       resource: { keys: [owner, repo] }
       capabilities:
         send_message: [add_issue_comment, issue_write]
         write_data: [push_files, create_or_update_file, delete_file]
   ```

2. Copy the rules in [`frontier-risk-rules.yaml`](frontier-risk-rules.yaml) to the **top** of your profile's `rules:` list, then add your own rules after them.

That declaration is the whole of the template's reach. A capability rule can never apply to a server that declared nothing (`capability_needs_declaration`), so pasting the template at the top cannot change what an undeclared connection may do.

## What the template is, and isn't

**The deny rules are a backstop against your own broad allow rules.** A call that matches no rule is denied anyway, so on a rule file that lists its allowed tools one by one, the deny rules change nothing. They start mattering when something later in your file — a catch-all `allow`, or a broad `server.*` rule — would otherwise let the call through. That is a real and common case, and it is what these rules are for. It is not the same as "these rules protect you from the tools."

**The ask rules do change what a profile does**, for any tool you declared as a send or an automated decision. On the GitHub profile that is `add_issue_comment` and `issue_write`, which are plain `allow` today. Read the two paragraphs below before adopting them.

### Two things to know

- **A deny or ask rule also applies when its argument is missing** (AgentGuard's safe direction). So the by-path R084 rule denies a write with no `path` at all, and a decision call with no `domain` needs a person.
- **Rules after the template can't loosen it, and the template outranks rules you write later.** That is the point of the proofs, and the cost of them. To let some sends through without a person (to known recipients, say), put a narrower allow rule *before* `send_message`, and accept that the proof no longer covers those sends.

## What is proved

For **every** policy and **every** list of rules `rest` placed after the template:

- a call caught by one of the template's **deny** rules gets the action deny (`template_deny`);
- a call caught by **any** of the template's rules never gets the action allow (`template_not_allow`).

Both follow from one general fact, `action_of_prefix`: if every rule in a prefix has a property and one of them applies, the first-match verdict has that property, whatever comes after.

Combined with the existing safety theorems, these become statements about whole sessions, for every policy whose rules start with the template, every approver, every starting session and every sequence of calls:

- `template_deny_never_runs`: a call caught by a deny rule is denied and never runs;
- `template_needs_person`: a call caught by any rule of the template is never allowed, and runs only if a person approves it.

Each rule also has its own theorem, below. Example sessions are checked at build time in [`lean/GuardTest/FrontierRisk.lean`](../lean/GuardTest/FrontierRisk.lean), including that an undeclared server is left entirely alone. [`tests/unit/test_frontier_risk.py`](../tests/unit/test_frontier_risk.py) checks that the YAML file matches the Lean list and that the real worker decides it the same way.

## The 40 items

### New: in the template (33 items, 20 rules)

| ID | AIR-Bench item | Rule | Theorem |
|---|---|---|---|
| R075, R076 | 1.1.1 Network intrusion, 1.1.2 Vulnerability probing | `network_scan` deny | `network_scan_denied` |
| R077, R082 | 1.1.3 Spoofing, 1.2.8 Packet forgery | `packet_forge` deny | `packet_forge_denied` |
| R080 | 1.1.6 Unauthorized network entry | `remote_access` deny | `remote_access_denied` |
| R081 | 1.2.7 Malware | `malware_exec` deny | `malware_exec_denied` |
| R083 | 1.2.9 Data tampering | `audit_tamper` deny | `audit_tamper_denied` |
| R084 | 1.2.10 Control override | `guard_config_write` deny, and `write_data` with `path: **agentguard/**` deny | `guard_config_write_denied`, `guard_config_path_denied` |
| R085, R086 | 1.3.11 System/Website impairment, 1.3.12 Network disruption | `service_disrupt` deny | `service_disrupt_denied` |
| R097–R106 | 2.5.11–2.5.20 Heavy machinery, transportation, energy grids, nuclear facilities, air traffic control, communication systems, water treatment, life support, weapon systems, emergency services | `operate_physical_system` deny | `operate_physical_system_denied` |
| R078, R079 | 1.1.4 Spear phishing, 1.1.5 Social engineering | `send_message` ask | `send_message_needs_person` |
| R087–R096 | 2.4.1–2.4.10 Financing, criminal justice, legal rights, employment, social scoring, housing, education, migration, insurance, profiling | `automated_decision` with `domain: …` ask (one rule each) | `automated_decision_needs_person` |
| R107 | 2.5.21 Other unauthorized actions | no rule needed: no match means deny | `air_2_5_21_unmatched_denied`, `unmatched_denied` |

**On R084.** The agent must not edit AgentGuard's own guardrails. Two rules, because there are two ways in: a connection with a dedicated configuration tool declares `guard_config_write`; any other tool it declared as writing data is caught by the path. Between them this covers every declared write tool, rather than one tool name — which is what an earlier draft of this template got wrong.

### Already covered (5)

| ID | Source | Item | How | Theorem |
|---|---|---|---|---|
| R065 | CAIS AI Dashboard | Agent Red Teaming: resist malicious use and prompt injection | AgentGuard does not resist injection; it limits what an injected agent can do. Labels and untrusted sources in the rule file | `no_untrusted_steering`, `no_exfiltration` |
| R066 | CAIS AI Dashboard | Confidentiality breaches | label confidential repositories; nothing read from them is written anywhere lower | `no_exfiltration` |
| R067 | CAIS AI Dashboard | Conflicting objectives (partly) | after outsider text, high-impact calls need a person, so injected goals can't act alone. Spotting the conflict itself is not covered. | `no_untrusted_steering` |
| R068 | CAIS AI Dashboard | Instruction hierarchy: information | the operator's data labelled above anything the agent writes to | `no_exfiltration` |
| R069 | CAIS AI Dashboard | Instruction hierarchy: actions | the operator's rules written as deny and ask rules | `deny_rule_always_denies`, `ask_rule_needs_person` |

### Needed a change to the rule language (2)

| ID | Source | Item | Status |
|---|---|---|---|
| R021 | FLI Index | Internal monitoring and control | **Done.** A person can stop a session and nothing runs after that: `kill_switch`, `stopped_sticky`. See [proofs.md](proofs.md). The oversight half — the agent never editing AgentGuard's own files — is R084 above. |
| R073 | CAIS AI Dashboard | Machiavelli: no power-seeking | **Proposal.** A `budget` field on rules (at most one `add_collaborator` per session, say), counted in the session. Statement to review: `BudgetNeverExceeded` — a run that starts within budget stays within budget. As [CONTRIBUTING.md](../CONTRIBUTING.md) requires, it must be reviewed by a person before anyone proves it. |
