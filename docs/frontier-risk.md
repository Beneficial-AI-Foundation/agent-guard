# The frontier-risk template

The [FLI AI Safety Index](https://futureoflife.org/index) (Summer 2026) and the four benchmarks it uses (AIR-Bench 2024, HELM Safety v1.0, TrustLLM, CAIS AI Dashboard) contain 388 safety rules in total. **40 of them are about what an agent is allowed to do**, so AgentGuard can enforce them and Lean can prove they hold. This page lists all 40 and says what covers each one.

- **33 rules** are new: the template in [`frontier-risk-rules.yaml`](frontier-risk-rules.yaml), proved in [`lean/Guard/Rulesets/FrontierRisk.lean`](../lean/Guard/Rulesets/FrontierRisk.lean).
- **5 rules** were already covered by AgentGuard's existing theorems.
- **2 rules** need a change to the rule language (budgets, a kill switch). They are proposals, not part of this change.

The rule wording and the choice of which rules fit are BAIF's interpretation (Nov 2026), not FLI's or the benchmark authors'. AIR-Bench rules read "refuse requests that facilitate …"; AgentGuard enforces only the **agent-action** part (the agent can't *do* it). Whether a model's text helps someone do it is outside AgentGuard.

## How to use the template

Copy the rules in [`frontier-risk-rules.yaml`](frontier-risk-rules.yaml) to the **top** of your profile's `rules:` list, then add your own rules after them.

**Tool names are placeholders.** `*.port_scan*` or `nuclear.*` say which tools a rule is meant to catch. Check each pattern against the real tool names of the MCP servers in your profile, and widen it if it misses one. Remember that `*` never matches `/`, so `financing*` does not match `financing/consumer`.

## What is proved

For **every** list of rules `rest` placed after the template:

- a call caught by one of the template's **deny** rules gets the action deny (`template_deny`);
- a call caught by **any** of the template's rules never gets the action allow (`template_not_allow`).

Both follow from one general fact, `action_of_prefix`: if every rule in a prefix has a property and one of them applies, the first-match verdict has that property, whatever comes after.

Combined with the existing safety theorems, these become statements about whole sessions. They hold for every policy whose rules start with the template, every approver, every starting session and every sequence of calls:

- `template_deny_never_runs`: a call caught by a deny rule is denied and never runs;
- `template_needs_person`: a call caught by any rule of the template is never allowed, and runs only if a person approves it.

Each rule also has its own theorem (`air_1_1_1_network_intrusion` and so on, below), stated as in the catalogue. Example sessions are checked at build time in [`lean/GuardTest/FrontierRisk.lean`](../lean/GuardTest/FrontierRisk.lean). [`tests/unit/test_frontier_risk.py`](../tests/unit/test_frontier_risk.py) checks that the YAML file matches the Lean list and that the real worker decides it the same way.

The template doesn't change the rule language: nothing under `lean/Guard/Spec/` changes.

### Two things to know

- **A deny or ask rule also applies when its argument is missing** (AgentGuard's safe direction). So the R084 rule denies a `push_files` call with no `path` at all, and a `decide_*` call with no `domain` needs a person.
- **Rules after the template can't loosen it.** That is the point of the proofs. To let some sends through without a person (for example, to known recipients), put a narrower allow rule *before* `*.send_*`, and accept that the proof no longer covers those sends.

## The 40 rules

### New: in the template (33)

| ID | Source | Item | Rule | Theorem |
|---|---|---|---|---|
| R075 | AIR-Bench | 1.1.1 Network intrusion | `*.port_scan*` deny | `air_1_1_1_network_intrusion` |
| R076 | AIR-Bench | 1.1.2 Vulnerability probing | `*.vuln_scan*` deny | `air_1_1_2_vulnerability_probing` |
| R077 | AIR-Bench | 1.1.3 Spoofing | `*.spoof_*` deny | `air_1_1_3_spoofing` |
| R078 | AIR-Bench | 1.1.4 Spear phishing | `*.send_*` ask | `air_1_1_4_spear_phishing` |
| R079 | AIR-Bench | 1.1.5 Social engineering | `*.send_*` ask | `air_1_1_5_social_engineering` |
| R080 | AIR-Bench | 1.1.6 Unauthorized network entry | `*.remote_login*` deny | `air_1_1_6_unauthorized_network_entry` |
| R081 | AIR-Bench | 1.2.7 Malware | `*.run_unsandboxed*` deny | `air_1_2_7_malware` |
| R082 | AIR-Bench | 1.2.8 Packet forgery | `*.raw_packet*` deny | `air_1_2_8_packet_forgery` |
| R083 | AIR-Bench | 1.2.9 Data tampering | `*.edit_audit_log*` deny | `air_1_2_9_data_tampering` |
| R084 | AIR-Bench | 1.2.10 Control override | `*.push_files` with `path: agentguard/**` deny | `air_1_2_10_control_override` |
| R085 | AIR-Bench | 1.3.11 System/Website impairment | `*.flood_*` deny | `air_1_3_11_system_impairment` |
| R086 | AIR-Bench | 1.3.12 Network disruption | `*.network_config*` deny | `air_1_3_12_network_disruption` |
| R087 | AIR-Bench | 2.4.1 Financing eligibility | `*.decide_*` with `domain: financing*` ask | `air_2_4_1_financing_eligibility` |
| R088 | AIR-Bench | 2.4.2 Criminal justice | `*.decide_*` with `domain: criminal*` ask | `air_2_4_2_criminal_justice` |
| R089 | AIR-Bench | 2.4.3 Legal rights | `*.decide_*` with `domain: legal*` ask | `air_2_4_3_legal_rights` |
| R090 | AIR-Bench | 2.4.4 Employment | `*.decide_*` with `domain: employment*` ask | `air_2_4_4_employment` |
| R091 | AIR-Bench | 2.4.5 Social scoring | `*.decide_*` with `domain: social_scoring*` ask | `air_2_4_5_social_scoring` |
| R092 | AIR-Bench | 2.4.6 Housing eligibility | `*.decide_*` with `domain: housing*` ask | `air_2_4_6_housing_eligibility` |
| R093 | AIR-Bench | 2.4.7 Education eligibility | `*.decide_*` with `domain: education*` ask | `air_2_4_7_education_eligibility` |
| R094 | AIR-Bench | 2.4.8 Migration eligibility | `*.decide_*` with `domain: migration*` ask | `air_2_4_8_migration_eligibility` |
| R095 | AIR-Bench | 2.4.9 Insurance eligibility | `*.decide_*` with `domain: insurance*` ask | `air_2_4_9_insurance_eligibility` |
| R096 | AIR-Bench | 2.4.10 Profiling | `*.decide_*` with `domain: profiling*` ask | `air_2_4_10_profiling` |
| R097 | AIR-Bench | 2.5.11 Heavy machinery | `machinery.*` deny | `air_2_5_11_heavy_machinery` |
| R098 | AIR-Bench | 2.5.12 Transportation | `transport.*` deny | `air_2_5_12_transportation` |
| R099 | AIR-Bench | 2.5.13 Energy/Electrical grids | `grid.*` deny | `air_2_5_13_energy_grids` |
| R100 | AIR-Bench | 2.5.14 Nuclear facilities | `nuclear.*` deny | `air_2_5_14_nuclear_facilities` |
| R101 | AIR-Bench | 2.5.15 Air traffic control | `aviation.*` deny | `air_2_5_15_air_traffic_control` |
| R102 | AIR-Bench | 2.5.16 Communication systems | `telecom.*` deny | `air_2_5_16_communication_systems` |
| R103 | AIR-Bench | 2.5.17 Water treatment | `water.*` deny | `air_2_5_17_water_treatment` |
| R104 | AIR-Bench | 2.5.18 Life support | `lifesupport.*` deny | `air_2_5_18_life_support` |
| R105 | AIR-Bench | 2.5.19 Weapon systems | `weapons.*` deny | `air_2_5_19_weapon_systems` |
| R106 | AIR-Bench | 2.5.20 Emergency services | `emergency.*` deny | `air_2_5_20_emergency_services` |
| R107 | AIR-Bench | 2.5.21 Other unauthorized actions | no rule needed: no match means deny | `air_2_5_21_unmatched_denied`, `unmatched_denied` |

### Already covered (5)

| ID | Source | Item | How | Theorem |
|---|---|---|---|---|
| R065 | CAIS AI Dashboard | Agent Red Teaming: resist malicious use and prompt injection | labels and untrusted sources in the rule file | `no_untrusted_steering`, `no_exfiltration` |
| R066 | CAIS AI Dashboard | Confidentiality breaches | label confidential repositories; nothing read from them is written anywhere lower | `no_exfiltration` |
| R067 | CAIS AI Dashboard | Conflicting objectives (partly) | after outsider text, high-impact calls need a person, so injected goals can't act alone. Spotting the conflict itself is not covered. | `no_untrusted_steering` |
| R068 | CAIS AI Dashboard | Instruction hierarchy: information | the operator's data labelled above anything the agent writes to | `no_exfiltration` |
| R069 | CAIS AI Dashboard | Instruction hierarchy: actions | the operator's rules written as deny and ask rules | `deny_rule_always_denies`, `ask_rule_needs_person` |

### Proposals: need a change to the rule language (2)

These change `lean/Guard/Spec/`. As [CONTRIBUTING.md](../CONTRIBUTING.md) requires, their statements must be reviewed by a person before anyone proves them, so they are not part of this change.

| ID | Source | Item | Proposal | Statement to review |
|---|---|---|---|---|
| R073 | CAIS AI Dashboard | Machiavelli: no power-seeking | **Budgets**: a `budget` field on rules (e.g. at most one `add_collaborator` per session), counted in the session | `BudgetNeverExceeded`: a run that starts within budget stays within budget |
| R021 | FLI Index | Internal monitoring and control | **Kill switch**: a stop signal from the console sets `Session.stopped`; nothing runs after it. (The oversight half, never editing AgentGuard's own files, is R084 above.) | `KillSwitch`: if the session is stopped, no call in the run is executed |
