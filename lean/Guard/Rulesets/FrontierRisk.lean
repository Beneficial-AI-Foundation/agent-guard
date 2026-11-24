import Guard.Spec.Semantics
import Guard.Proofs.Safety

/-!
# The frontier-risk template

Rules taken from the FLI AI Safety Index (Summer 2026) and the benchmarks it
uses (AIR-Bench 2024, CAIS AI Dashboard) that are about **what an agent may do**,
written as AgentGuard rules. The full mapping, rule by rule, is in
`docs/frontier-risk.md`; the same rules as a rule file are in
`docs/frontier-risk-rules.yaml`.

The template is meant to sit **at the top** of a rule file. Every theorem below
holds for `frontierTemplate ++ rest` for **every** list `rest`, so the
guarantees survive any rules added after the template, including a catch-all
`allow`.

Tool names are placeholders (`*.port_scan*`, `nuclear.*`): they say which tools
the rule is meant to catch, and must be checked against the real MCP servers a
profile connects to.

The template keeps every `deny` rule before every `ask` rule, so a call that
hits a deny rule is denied even if it also hits an ask rule.

Omitted attributes take their safe values (`effect: readwrite`,
`untrusted: true`, `highImpact: true`), as in a rule file.

No change to the rule language: this file only uses `Guard.Spec` and the
theorems in `Guard.Proofs.Safety`.
-/

namespace Guard.FrontierRisk

open Guard

/-- A deny rule with the safe defaults for omitted attributes. -/
def denyRule (tool : String) (conds : List Cond := []) : Rule :=
  { tool, conds, action := .deny, effect := .readwrite, untrusted := true, highImpact := true }

/-- An ask rule with the safe defaults for omitted attributes. -/
def askRule (tool : String) (conds : List Cond := []) : Rule :=
  { tool, conds, action := .ask, effect := .readwrite, untrusted := true, highImpact := true }

/-- An automated decision in `domain` needs a person. -/
def decideRule (domain : String) : Rule :=
  askRule "*.decide_*" [⟨"domain", [domain]⟩]

/-! ## The rules -/

/-- Things an agent never does. -/
def frontierDeny : List Rule :=
  [ denyRule "*.port_scan*",          -- R075 AIR-Bench 1.1.1  Network intrusion
    denyRule "*.vuln_scan*",          -- R076 AIR-Bench 1.1.2  Vulnerability probing
    denyRule "*.spoof_*",             -- R077 AIR-Bench 1.1.3  Spoofing
    denyRule "*.remote_login*",       -- R080 AIR-Bench 1.1.6  Unauthorized network entry
    denyRule "*.run_unsandboxed*",    -- R081 AIR-Bench 1.2.7  Malware
    denyRule "*.raw_packet*",         -- R082 AIR-Bench 1.2.8  Packet forgery
    denyRule "*.edit_audit_log*",     -- R083 AIR-Bench 1.2.9  Data tampering
    denyRule "*.push_files" [⟨"path", ["agentguard/**"]⟩],
                                      -- R084 AIR-Bench 1.2.10 Control override
    denyRule "*.flood_*",             -- R085 AIR-Bench 1.3.11 System/Website impairment
    denyRule "*.network_config*",     -- R086 AIR-Bench 1.3.12 Network disruption
    denyRule "machinery.*",           -- R097 AIR-Bench 2.5.11 Heavy machinery
    denyRule "transport.*",           -- R098 AIR-Bench 2.5.12 Transportation
    denyRule "grid.*",                -- R099 AIR-Bench 2.5.13 Energy/Electrical grids
    denyRule "nuclear.*",             -- R100 AIR-Bench 2.5.14 Nuclear facilities
    denyRule "aviation.*",            -- R101 AIR-Bench 2.5.15 Air traffic control
    denyRule "telecom.*",             -- R102 AIR-Bench 2.5.16 Communication systems
    denyRule "water.*",               -- R103 AIR-Bench 2.5.17 Water treatment
    denyRule "lifesupport.*",         -- R104 AIR-Bench 2.5.18 Life support
    denyRule "weapons.*",             -- R105 AIR-Bench 2.5.19 Weapon systems
    denyRule "emergency.*" ]          -- R106 AIR-Bench 2.5.20 Emergency services

/-- Things an agent does only with a person's approval. -/
def frontierAsk : List Rule :=
  [ askRule "*.send_*",               -- R078, R079 AIR-Bench 1.1.4, 1.1.5 Phishing, social engineering
    decideRule "financing*",          -- R087 AIR-Bench 2.4.1  Financing eligibility
    decideRule "criminal*",           -- R088 AIR-Bench 2.4.2  Criminal justice
    decideRule "legal*",              -- R089 AIR-Bench 2.4.3  Legal rights
    decideRule "employment*",         -- R090 AIR-Bench 2.4.4  Employment
    decideRule "social_scoring*",     -- R091 AIR-Bench 2.4.5  Social scoring
    decideRule "housing*",            -- R092 AIR-Bench 2.4.6  Housing eligibility
    decideRule "education*",          -- R093 AIR-Bench 2.4.7  Education eligibility
    decideRule "migration*",          -- R094 AIR-Bench 2.4.8  Migration eligibility
    decideRule "insurance*",          -- R095 AIR-Bench 2.4.9  Insurance eligibility
    decideRule "profiling*" ]         -- R096 AIR-Bench 2.4.10 Profiling

/-- The template: all deny rules, then all ask rules. -/
def frontierTemplate : List Rule :=
  frontierDeny ++ frontierAsk

/-! ## General facts about a prefix of rules -/

/-- If some rule of `rules` applies, the first match in `rules ++ rest` is one of `rules`. -/
theorem firstMatchFrom_prefix (c : ToolCall) (rest : List Rule) :
    ∀ (rules : List Rule) (i : Nat), (∃ r ∈ rules, r.Applies c) →
      ∃ j, ∃ r ∈ rules, firstMatchFrom c i (rules ++ rest) = some (j, r)
  | [], _, ⟨_, hr, _⟩ => by simp at hr
  | r :: rs, i, ⟨r', hr', ha'⟩ => by
    by_cases h : r.Applies c
    · exact ⟨i, r, by simp, by simp [firstMatchFrom, h]⟩
    · have hin : r' ∈ rs := by
        rcases List.mem_cons.mp hr' with rfl | hin
        · exact absurd ha' h
        · exact hin
      obtain ⟨j, r'', hr'', heq⟩ := firstMatchFrom_prefix c rest rs (i + 1) ⟨r', hin, ha'⟩
      exact ⟨j, r'', List.mem_cons_of_mem _ hr'', by simp [firstMatchFrom, h, heq]⟩

/-- **Rules added later cannot override a prefix.** If every rule of `rules` has an
action with property `P` and one of them applies to the call, the verdict of
`rules ++ rest` has property `P`, whatever `rest` is. -/
theorem action_of_prefix {P : Action → Prop} (rules rest : List Rule) (c : ToolCall)
    (hall : ∀ r ∈ rules, P r.action) (hex : ∃ r ∈ rules, r.Applies c) :
    P (action (rules ++ rest) c) := by
  obtain ⟨j, r, hr, heq⟩ := firstMatchFrom_prefix c rest rules 0 hex
  simp only [action, firstMatch, heq]
  exact hall r hr

/-- A rule without conditions applies when its tool pattern matches. -/
theorem applies_of_glob (r : Rule) (c : ToolCall) (hc : r.conds = [])
    (h : Glob r.tool c.name) : r.Applies c :=
  ⟨h, by simp [hc]⟩

/-- A deny or ask rule with one condition `k: pat` applies when its tool pattern
matches and some value of `k` matches `pat`. -/
theorem applies_of_value (r : Rule) (c : ToolCall) (k pat : String)
    (hc : r.conds = [⟨k, [pat]⟩]) (hna : r.action ≠ .allow)
    (h : Glob r.tool c.name) (hv : ∃ v ∈ argValues c.args k, Glob pat v) : r.Applies c := by
  refine ⟨h, fun cd hcd => ?_⟩
  rw [hc, List.mem_singleton] at hcd
  subst hcd
  simp only [Cond.Holds, hna, ↓reduceIte]
  obtain ⟨v, hv, hg⟩ := hv
  exact Or.inr ⟨v, hv, pat, List.mem_singleton.mpr rfl, hg⟩

/-! ## What the template guarantees -/

theorem frontierDeny_all_deny : ∀ r ∈ frontierDeny, r.action = .deny := by
  simp [frontierDeny, denyRule]

theorem frontierTemplate_never_allows : ∀ r ∈ frontierTemplate, r.action ≠ .allow := by
  simp [frontierTemplate, frontierDeny, frontierAsk, denyRule, askRule, decideRule]

/-- A call caught by a deny rule of the template is denied, whatever follows it. -/
theorem template_deny (rest : List Rule) (c : ToolCall)
    (hex : ∃ r ∈ frontierDeny, r.Applies c) :
    action (frontierTemplate ++ rest) c = .deny := by
  rw [frontierTemplate, List.append_assoc]
  exact action_of_prefix (P := (· = .deny)) _ _ c frontierDeny_all_deny hex

/-- A call caught by any rule of the template is never allowed by a rule, whatever
follows it. -/
theorem template_not_allow (rest : List Rule) (c : ToolCall)
    (hex : ∃ r ∈ frontierTemplate, r.Applies c) :
    action (frontierTemplate ++ rest) c ≠ .allow :=
  action_of_prefix (P := (· ≠ .allow)) _ _ c frontierTemplate_never_allows hex

theorem ask_in_template (c : ToolCall) (r : Rule) (hr : r ∈ frontierAsk)
    (ha : r.Applies c) : ∃ r ∈ frontierTemplate, r.Applies c :=
  ⟨r, List.mem_append_right _ hr, ha⟩

/-- An automated decision in a domain matching `domain` is never allowed by a rule. -/
theorem decide_not_allow (domain : String) (hr : decideRule domain ∈ frontierAsk)
    (rest : List Rule) (c : ToolCall)
    (h : Glob "*.decide_*" c.name) (hv : ∃ v ∈ argValues c.args "domain", Glob domain v) :
    action (frontierTemplate ++ rest) c ≠ .allow :=
  template_not_allow rest c <| ask_in_template c _ hr <|
    applies_of_value _ c "domain" domain rfl (by simp [decideRule, askRule]) h hv

/-! ## One theorem per rule (AIR-Bench 2024 numbering) -/

section PerRule

variable (rest : List Rule) (c : ToolCall)

/-- Deny rules without conditions. -/
private theorem deny_glob (tool : String) (hr : denyRule tool ∈ frontierDeny)
    (h : Glob tool c.name) : action (frontierTemplate ++ rest) c = .deny :=
  template_deny rest c ⟨_, hr, applies_of_glob _ c rfl h⟩

theorem air_1_1_1_network_intrusion (h : Glob "*.port_scan*" c.name) :
    action (frontierTemplate ++ rest) c = .deny :=
  deny_glob rest c _ (by simp [frontierDeny]) h

theorem air_1_1_2_vulnerability_probing (h : Glob "*.vuln_scan*" c.name) :
    action (frontierTemplate ++ rest) c = .deny :=
  deny_glob rest c _ (by simp [frontierDeny]) h

theorem air_1_1_3_spoofing (h : Glob "*.spoof_*" c.name) :
    action (frontierTemplate ++ rest) c = .deny :=
  deny_glob rest c _ (by simp [frontierDeny]) h

theorem air_1_1_4_spear_phishing (h : Glob "*.send_*" c.name) :
    action (frontierTemplate ++ rest) c ≠ .allow :=
  template_not_allow rest c <|
    ask_in_template c _ (by simp [frontierAsk]) (applies_of_glob (askRule "*.send_*") c rfl h)

theorem air_1_1_5_social_engineering (h : Glob "*.send_*" c.name) :
    action (frontierTemplate ++ rest) c ≠ .allow :=
  air_1_1_4_spear_phishing rest c h

theorem air_1_1_6_unauthorized_network_entry (h : Glob "*.remote_login*" c.name) :
    action (frontierTemplate ++ rest) c = .deny :=
  deny_glob rest c _ (by simp [frontierDeny]) h

theorem air_1_2_7_malware (h : Glob "*.run_unsandboxed*" c.name) :
    action (frontierTemplate ++ rest) c = .deny :=
  deny_glob rest c _ (by simp [frontierDeny]) h

theorem air_1_2_8_packet_forgery (h : Glob "*.raw_packet*" c.name) :
    action (frontierTemplate ++ rest) c = .deny :=
  deny_glob rest c _ (by simp [frontierDeny]) h

theorem air_1_2_9_data_tampering (h : Glob "*.edit_audit_log*" c.name) :
    action (frontierTemplate ++ rest) c = .deny :=
  deny_glob rest c _ (by simp [frontierDeny]) h

/-- A push that touches AgentGuard's own files is denied. (As for every deny rule,
a push with no `path` at all is denied too.) -/
theorem air_1_2_10_control_override (h : Glob "*.push_files" c.name)
    (hv : ∃ v ∈ argValues c.args "path", Glob "agentguard/**" v) :
    action (frontierTemplate ++ rest) c = .deny :=
  template_deny rest c ⟨_, by simp [frontierDeny],
    applies_of_value (denyRule "*.push_files" [⟨"path", ["agentguard/**"]⟩]) c
      "path" "agentguard/**" rfl (by simp [denyRule]) h hv⟩

theorem air_1_3_11_system_impairment (h : Glob "*.flood_*" c.name) :
    action (frontierTemplate ++ rest) c = .deny :=
  deny_glob rest c _ (by simp [frontierDeny]) h

theorem air_1_3_12_network_disruption (h : Glob "*.network_config*" c.name) :
    action (frontierTemplate ++ rest) c = .deny :=
  deny_glob rest c _ (by simp [frontierDeny]) h

theorem air_2_4_1_financing_eligibility (h : Glob "*.decide_*" c.name)
    (hv : ∃ v ∈ argValues c.args "domain", Glob "financing*" v) :
    action (frontierTemplate ++ rest) c ≠ .allow :=
  decide_not_allow _ (by simp [frontierAsk]) rest c h hv

theorem air_2_4_2_criminal_justice (h : Glob "*.decide_*" c.name)
    (hv : ∃ v ∈ argValues c.args "domain", Glob "criminal*" v) :
    action (frontierTemplate ++ rest) c ≠ .allow :=
  decide_not_allow _ (by simp [frontierAsk]) rest c h hv

theorem air_2_4_3_legal_rights (h : Glob "*.decide_*" c.name)
    (hv : ∃ v ∈ argValues c.args "domain", Glob "legal*" v) :
    action (frontierTemplate ++ rest) c ≠ .allow :=
  decide_not_allow _ (by simp [frontierAsk]) rest c h hv

theorem air_2_4_4_employment (h : Glob "*.decide_*" c.name)
    (hv : ∃ v ∈ argValues c.args "domain", Glob "employment*" v) :
    action (frontierTemplate ++ rest) c ≠ .allow :=
  decide_not_allow _ (by simp [frontierAsk]) rest c h hv

theorem air_2_4_5_social_scoring (h : Glob "*.decide_*" c.name)
    (hv : ∃ v ∈ argValues c.args "domain", Glob "social_scoring*" v) :
    action (frontierTemplate ++ rest) c ≠ .allow :=
  decide_not_allow _ (by simp [frontierAsk]) rest c h hv

theorem air_2_4_6_housing_eligibility (h : Glob "*.decide_*" c.name)
    (hv : ∃ v ∈ argValues c.args "domain", Glob "housing*" v) :
    action (frontierTemplate ++ rest) c ≠ .allow :=
  decide_not_allow _ (by simp [frontierAsk]) rest c h hv

theorem air_2_4_7_education_eligibility (h : Glob "*.decide_*" c.name)
    (hv : ∃ v ∈ argValues c.args "domain", Glob "education*" v) :
    action (frontierTemplate ++ rest) c ≠ .allow :=
  decide_not_allow _ (by simp [frontierAsk]) rest c h hv

theorem air_2_4_8_migration_eligibility (h : Glob "*.decide_*" c.name)
    (hv : ∃ v ∈ argValues c.args "domain", Glob "migration*" v) :
    action (frontierTemplate ++ rest) c ≠ .allow :=
  decide_not_allow _ (by simp [frontierAsk]) rest c h hv

theorem air_2_4_9_insurance_eligibility (h : Glob "*.decide_*" c.name)
    (hv : ∃ v ∈ argValues c.args "domain", Glob "insurance*" v) :
    action (frontierTemplate ++ rest) c ≠ .allow :=
  decide_not_allow _ (by simp [frontierAsk]) rest c h hv

theorem air_2_4_10_profiling (h : Glob "*.decide_*" c.name)
    (hv : ∃ v ∈ argValues c.args "domain", Glob "profiling*" v) :
    action (frontierTemplate ++ rest) c ≠ .allow :=
  decide_not_allow _ (by simp [frontierAsk]) rest c h hv

theorem air_2_5_11_heavy_machinery (h : Glob "machinery.*" c.name) :
    action (frontierTemplate ++ rest) c = .deny :=
  deny_glob rest c _ (by simp [frontierDeny]) h

theorem air_2_5_12_transportation (h : Glob "transport.*" c.name) :
    action (frontierTemplate ++ rest) c = .deny :=
  deny_glob rest c _ (by simp [frontierDeny]) h

theorem air_2_5_13_energy_grids (h : Glob "grid.*" c.name) :
    action (frontierTemplate ++ rest) c = .deny :=
  deny_glob rest c _ (by simp [frontierDeny]) h

theorem air_2_5_14_nuclear_facilities (h : Glob "nuclear.*" c.name) :
    action (frontierTemplate ++ rest) c = .deny :=
  deny_glob rest c _ (by simp [frontierDeny]) h

theorem air_2_5_15_air_traffic_control (h : Glob "aviation.*" c.name) :
    action (frontierTemplate ++ rest) c = .deny :=
  deny_glob rest c _ (by simp [frontierDeny]) h

theorem air_2_5_16_communication_systems (h : Glob "telecom.*" c.name) :
    action (frontierTemplate ++ rest) c = .deny :=
  deny_glob rest c _ (by simp [frontierDeny]) h

theorem air_2_5_17_water_treatment (h : Glob "water.*" c.name) :
    action (frontierTemplate ++ rest) c = .deny :=
  deny_glob rest c _ (by simp [frontierDeny]) h

theorem air_2_5_18_life_support (h : Glob "lifesupport.*" c.name) :
    action (frontierTemplate ++ rest) c = .deny :=
  deny_glob rest c _ (by simp [frontierDeny]) h

theorem air_2_5_19_weapon_systems (h : Glob "weapons.*" c.name) :
    action (frontierTemplate ++ rest) c = .deny :=
  deny_glob rest c _ (by simp [frontierDeny]) h

theorem air_2_5_20_emergency_services (h : Glob "emergency.*" c.name) :
    action (frontierTemplate ++ rest) c = .deny :=
  deny_glob rest c _ (by simp [frontierDeny]) h

end PerRule

/-- R107 AIR-Bench 2.5.21 Other unauthorized actions: needs no rule of its own,
because a call that no rule matches is denied. -/
theorem air_2_5_21_unmatched_denied (rules : List Rule) (c : ToolCall)
    (h : firstMatch rules c = none) : action rules c = .deny := by
  simp [action, h]

/-! ## Over whole sessions

The theorems above are about the first matching rule. With the safety theorems
of `Guard.Proofs.Safety` they become statements about every call the gateway
decides: for every policy whose rules start with the template, every approver,
every starting session and every sequence of calls. -/

/-- A call caught by a deny rule of the template never runs. -/
theorem template_deny_never_runs (p : Policy) (rest : List Rule)
    (hp : p.rules = frontierTemplate ++ rest) :
    ∀ approve s cs, ∀ e ∈ run p approve s cs, (∃ r ∈ frontierDeny, r.Applies e.call) →
      e.decision.verdict = .deny ∧ e.executed = false := by
  intro approve s cs e he hex
  exact deny_rule_always_denies p approve s cs e he (hp ▸ template_deny rest e.call hex)

/-- A call caught by any rule of the template is never allowed, and runs only if a
person approves it. -/
theorem template_needs_person (p : Policy) (rest : List Rule)
    (hp : p.rules = frontierTemplate ++ rest) :
    ∀ approve s cs, ∀ e ∈ run p approve s cs, (∃ r ∈ frontierTemplate, r.Applies e.call) →
      e.decision.verdict ≠ .allow ∧
        (e.executed = true → approve e.before e.call = true) := by
  intro approve s cs e he hex
  have hna : action p.rules e.call ≠ .allow := hp ▸ template_not_allow rest e.call hex
  cases ha : action p.rules e.call with
  | allow => exact absurd ha hna
  | deny =>
    obtain ⟨hv, hx⟩ := deny_rule_always_denies p approve s cs e he ha
    exact ⟨by rw [hv]; decide, fun h => by rw [hx] at h; cases h⟩
  | ask => exact ask_rule_needs_person p approve s cs e he ha

end Guard.FrontierRisk
