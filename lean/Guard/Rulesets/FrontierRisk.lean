import Guard.Spec.Semantics
import Guard.Proofs.Safety

/-!
# The frontier-risk template

Rules taken from the FLI AI Safety Index (Summer 2026) and the benchmarks it
uses (AIR-Bench 2024, CAIS AI Dashboard) that are about **what an agent may
do**, written as AgentGuard rules. The full mapping, item by item, is in
`docs/frontier-risk.md`; the same rules as a rule file are in
`docs/frontier-risk-rules.yaml`.

Every rule selects on a **capability**, not on a tool name. So the template
says nothing about what anyone's tools are called: it catches exactly the tools
a connection declared, in its own `servers` block, as scanning a network or
sending a message or operating a physical system. A capability rule can never
reach a server that declared nothing (`capability_needs_declaration`), so
pasting the template at the top of a rule file cannot change what any
undeclared server may do.

The template is meant to sit **at the top** of a rule file. Every theorem below
holds for `frontierTemplate ++ rest` for **every** list `rest`, so the
guarantees survive any rules added after the template, including a catch-all
`allow`.

The template keeps every `deny` rule before every `ask` rule, so a call that
hits a deny rule is denied even if it also hits an ask rule.

Omitted attributes take their safe values (`effect: readwrite`,
`untrusted: true`, `highImpact: true`), as in a rule file.

No change to the rule language: this file only uses `Guard.Spec` and the
theorems in `Guard.Proofs.Safety`.
-/

namespace Guard.FrontierRisk

open Guard

/-! ## `**` matches every tool name

A capability rule leaves `tool` at `**`; the selection is done by the
capability. -/

theorem glob_dstar (s : String) : Glob "**" s := by
  have h : tokenize "**".toList = [Tok.dstar] := by decide
  show Matches (tokenize "**".toList) s.toList
  rw [h]
  induction s.toList with
  | nil => exact .dstarNone .nil
  | cons _ _ ih => exact .dstarMore ih

/-! ## The rules -/

/-- A deny rule on a capability, with the safe defaults for omitted attributes. -/
def denyCap (cp : Capability) : Rule :=
  { tool := "**", cap := some cp, conds := [], action := .deny,
    effect := .readwrite, untrusted := true, highImpact := true }

/-- An ask rule on a capability. -/
def askCap (cp : Capability) (conds : List Cond := []) : Rule :=
  { tool := "**", cap := some cp, conds, action := .ask,
    effect := .readwrite, untrusted := true, highImpact := true }

/-- An automated decision in `domain` needs a person. -/
def decideRule (domain : String) : Rule :=
  askCap .automatedDecision [⟨"domain", [domain]⟩]

/-- Writing AgentGuard's own files, by whatever tool a connection declared as
writing data. A connection with a dedicated configuration tool declares
`guard_config_write` instead, and is caught by the rule above. -/
def guardConfigByPath : Rule :=
  { tool := "**", cap := some .writeData, conds := [⟨"path", ["**agentguard/**"]⟩],
    action := .deny, effect := .readwrite, untrusted := true, highImpact := true }

/-- Things an agent never does. -/
def frontierDeny : List Rule :=
  [ denyCap .networkScan,           -- R075, R076  AIR-Bench 1.1.1, 1.1.2
    denyCap .packetForge,           -- R077, R082  AIR-Bench 1.1.3, 1.2.8
    denyCap .remoteAccess,          -- R080        AIR-Bench 1.1.6
    denyCap .malwareExec,           -- R081        AIR-Bench 1.2.7
    denyCap .auditTamper,           -- R083        AIR-Bench 1.2.9
    denyCap .guardConfigWrite,      -- R084        AIR-Bench 1.2.10
    guardConfigByPath,              -- R084, by path rather than by tool
    denyCap .serviceDisrupt,        -- R085, R086  AIR-Bench 1.3.11, 1.3.12
    denyCap .operatePhysicalSystem ] -- R097–R106  AIR-Bench 2.5.11–2.5.20

/-- Things an agent does only with a person's approval. -/
def frontierAsk : List Rule :=
  [ askCap .sendMessage,            -- R078, R079  AIR-Bench 1.1.4, 1.1.5
    decideRule "financing*",        -- R087 AIR-Bench 2.4.1
    decideRule "criminal*",         -- R088 AIR-Bench 2.4.2
    decideRule "legal*",            -- R089 AIR-Bench 2.4.3
    decideRule "employment*",       -- R090 AIR-Bench 2.4.4
    decideRule "social_scoring*",   -- R091 AIR-Bench 2.4.5
    decideRule "housing*",          -- R092 AIR-Bench 2.4.6
    decideRule "education*",        -- R093 AIR-Bench 2.4.7
    decideRule "migration*",        -- R094 AIR-Bench 2.4.8
    decideRule "insurance*",        -- R095 AIR-Bench 2.4.9
    decideRule "profiling*" ]       -- R096 AIR-Bench 2.4.10

/-- The template: all deny rules, then all ask rules. -/
def frontierTemplate : List Rule :=
  frontierDeny ++ frontierAsk

/-! ## General facts about a prefix of rules -/

/-- If some rule of `rules` applies, the first match in `rules ++ rest` is one of `rules`. -/
theorem firstMatchFrom_prefix (p : Policy) (c : ToolCall) (rest : List Rule) :
    ∀ (rules : List Rule) (i : Nat), (∃ r ∈ rules, r.Applies p c) →
      ∃ j, ∃ r ∈ rules, firstMatchFrom p c i (rules ++ rest) = some (j, r)
  | [], _, ⟨_, hr, _⟩ => by simp at hr
  | r :: rs, i, ⟨r', hr', ha'⟩ => by
    by_cases h : r.Applies p c
    · exact ⟨i, r, by simp, by simp [firstMatchFrom, h]⟩
    · have hin : r' ∈ rs := by
        rcases List.mem_cons.mp hr' with rfl | hin
        · exact absurd ha' h
        · exact hin
      obtain ⟨j, r'', hr'', heq⟩ := firstMatchFrom_prefix p c rest rs (i + 1) ⟨r', hin, ha'⟩
      exact ⟨j, r'', List.mem_cons_of_mem _ hr'', by simp [firstMatchFrom, h, heq]⟩

/-- **Rules added later cannot override a prefix.** If every rule of `rules` has an
action with property `P` and one of them applies to the call, the verdict of
`rules ++ rest` has property `P`, whatever `rest` is. -/
theorem action_of_prefix {P : Action → Prop} (p : Policy) (rules rest : List Rule)
    (c : ToolCall) (hall : ∀ r ∈ rules, P r.action) (hex : ∃ r ∈ rules, r.Applies p c) :
    P (action p (rules ++ rest) c) := by
  obtain ⟨j, r, hr, heq⟩ := firstMatchFrom_prefix p c rest rules 0 hex
  simp only [action, firstMatch, heq]
  exact hall r hr

/-! ## When a template rule applies -/

/-- A deny rule applies exactly when the call has its capability. -/
theorem denyCap_applies (p : Policy) (c : ToolCall) (cp : Capability)
    (h : cp ∈ capsOf p c) : (denyCap cp).Applies p c :=
  ⟨glob_dstar _, by simpa [denyCap, Rule.CapHolds] using h, by simp [denyCap]⟩

/-- The same for an unconditional ask rule. -/
theorem askCap_applies (p : Policy) (c : ToolCall) (cp : Capability)
    (h : cp ∈ capsOf p c) : (askCap cp).Applies p c :=
  ⟨glob_dstar _, by simpa [askCap, Rule.CapHolds] using h, by simp [askCap]⟩

/-- A deny or ask rule selecting on a capability and one condition `k: pat`
applies when the call has the capability and some value of `k` matches. (As for
every deny or ask rule, a call with no `k` at all applies too: the safe
direction.) -/
theorem capCond_applies (p : Policy) (c : ToolCall) (r : Rule) (cp : Capability)
    (k pat : String) (ht : r.tool = "**") (hcp : r.cap = some cp)
    (hcd : r.conds = [⟨k, [pat]⟩]) (hna : r.action ≠ .allow)
    (hcap : cp ∈ capsOf p c) (hv : ∃ v ∈ argValues c.args k, Glob pat v) :
    r.Applies p c := by
  refine ⟨ht ▸ glob_dstar _, by simpa [Rule.CapHolds, hcp] using hcap, fun cd hc => ?_⟩
  rw [hcd, List.mem_singleton] at hc
  subst hc
  simp only [Cond.Holds, hna, ↓reduceIte]
  obtain ⟨v, hv, hg⟩ := hv
  exact Or.inr ⟨v, hv, pat, List.mem_singleton.mpr rfl, hg⟩

theorem decideRule_applies (p : Policy) (c : ToolCall) (domain : String)
    (hc : Capability.automatedDecision ∈ capsOf p c)
    (hv : ∃ v ∈ argValues c.args "domain", Glob domain v) :
    (decideRule domain).Applies p c :=
  capCond_applies p c _ _ "domain" domain rfl rfl rfl (by simp [decideRule, askCap]) hc hv

theorem guardConfigByPath_applies (p : Policy) (c : ToolCall)
    (hc : Capability.writeData ∈ capsOf p c)
    (hv : ∃ v ∈ argValues c.args "path", Glob "**agentguard/**" v) :
    guardConfigByPath.Applies p c :=
  capCond_applies p c _ _ "path" "**agentguard/**" rfl rfl rfl
    (by simp [guardConfigByPath]) hc hv

/-! ## What the template guarantees -/

theorem frontierDeny_all_deny : ∀ r ∈ frontierDeny, r.action = .deny := by
  simp [frontierDeny, denyCap, guardConfigByPath]

theorem frontierTemplate_never_allows : ∀ r ∈ frontierTemplate, r.action ≠ .allow := by
  simp [frontierTemplate, frontierDeny, frontierAsk, denyCap, askCap, decideRule,
    guardConfigByPath]

/-- A call caught by a deny rule of the template is denied, whatever follows it. -/
theorem template_deny (p : Policy) (rest : List Rule) (c : ToolCall)
    (hex : ∃ r ∈ frontierDeny, r.Applies p c) :
    action p (frontierTemplate ++ rest) c = .deny := by
  rw [frontierTemplate, List.append_assoc]
  exact action_of_prefix (P := (· = .deny)) p _ _ c frontierDeny_all_deny hex

/-- A call caught by any rule of the template is never allowed by a rule. -/
theorem template_not_allow (p : Policy) (rest : List Rule) (c : ToolCall)
    (hex : ∃ r ∈ frontierTemplate, r.Applies p c) :
    action p (frontierTemplate ++ rest) c ≠ .allow :=
  action_of_prefix (P := (· ≠ .allow)) p _ _ c frontierTemplate_never_allows hex

theorem ask_in_template (p : Policy) (c : ToolCall) (r : Rule) (hr : r ∈ frontierAsk)
    (ha : r.Applies p c) : ∃ r ∈ frontierTemplate, r.Applies p c :=
  ⟨r, List.mem_append_right _ hr, ha⟩

/-! ## One theorem per capability

Each is stated for every policy, so it says: whatever your connections are, if
one of them declared this tool as doing this thing, the template decides it. -/

section PerCapability

variable (p : Policy) (rest : List Rule) (c : ToolCall)

private theorem deny_of_cap (cp : Capability) (hr : denyCap cp ∈ frontierDeny)
    (h : cp ∈ capsOf p c) : action p (frontierTemplate ++ rest) c = .deny :=
  template_deny p rest c ⟨_, hr, denyCap_applies p c cp h⟩

/-- R075, R076 — AIR-Bench 1.1.1 Network intrusion, 1.1.2 Vulnerability probing. -/
theorem network_scan_denied (h : Capability.networkScan ∈ capsOf p c) :
    action p (frontierTemplate ++ rest) c = .deny :=
  deny_of_cap p rest c _ (by simp [frontierDeny]) h

/-- R077, R082 — AIR-Bench 1.1.3 Spoofing, 1.2.8 Packet forgery. -/
theorem packet_forge_denied (h : Capability.packetForge ∈ capsOf p c) :
    action p (frontierTemplate ++ rest) c = .deny :=
  deny_of_cap p rest c _ (by simp [frontierDeny]) h

/-- R080 — AIR-Bench 1.1.6 Unauthorized network entry. -/
theorem remote_access_denied (h : Capability.remoteAccess ∈ capsOf p c) :
    action p (frontierTemplate ++ rest) c = .deny :=
  deny_of_cap p rest c _ (by simp [frontierDeny]) h

/-- R081 — AIR-Bench 1.2.7 Malware. -/
theorem malware_exec_denied (h : Capability.malwareExec ∈ capsOf p c) :
    action p (frontierTemplate ++ rest) c = .deny :=
  deny_of_cap p rest c _ (by simp [frontierDeny]) h

/-- R083 — AIR-Bench 1.2.9 Data tampering. -/
theorem audit_tamper_denied (h : Capability.auditTamper ∈ capsOf p c) :
    action p (frontierTemplate ++ rest) c = .deny :=
  deny_of_cap p rest c _ (by simp [frontierDeny]) h

/-- R084 — AIR-Bench 1.2.10 Control override: the agent never writes AgentGuard's
own configuration. Which tools those are is the connection's declaration, so this
covers every way that connection can write, not one tool name. -/
theorem guard_config_write_denied (h : Capability.guardConfigWrite ∈ capsOf p c) :
    action p (frontierTemplate ++ rest) c = .deny :=
  deny_of_cap p rest c _ (by simp [frontierDeny]) h

/-- R084 again, the other way in: any tool a connection declared as writing data,
when a path names AgentGuard's own files. Between this and the rule above, the
agent cannot edit its own guardrails through any declared write tool. -/
theorem guard_config_path_denied (hc : Capability.writeData ∈ capsOf p c)
    (hv : ∃ v ∈ argValues c.args "path", Glob "**agentguard/**" v) :
    action p (frontierTemplate ++ rest) c = .deny :=
  template_deny p rest c ⟨_, by simp [frontierDeny], guardConfigByPath_applies p c hc hv⟩

/-- R085, R086 — AIR-Bench 1.3.11 System/Website impairment, 1.3.12 Network disruption. -/
theorem service_disrupt_denied (h : Capability.serviceDisrupt ∈ capsOf p c) :
    action p (frontierTemplate ++ rest) c = .deny :=
  deny_of_cap p rest c _ (by simp [frontierDeny]) h

/-- R097–R106 — AIR-Bench 2.5.11–2.5.20: heavy machinery, transportation, energy
grids, nuclear facilities, air traffic control, communication systems, water
treatment, life support, weapon systems, emergency services. -/
theorem operate_physical_system_denied (h : Capability.operatePhysicalSystem ∈ capsOf p c) :
    action p (frontierTemplate ++ rest) c = .deny :=
  deny_of_cap p rest c _ (by simp [frontierDeny]) h

/-- R078, R079 — AIR-Bench 1.1.4 Spear phishing, 1.1.5 Social engineering. -/
theorem send_message_needs_person (h : Capability.sendMessage ∈ capsOf p c) :
    action p (frontierTemplate ++ rest) c ≠ .allow :=
  template_not_allow p rest c <|
    ask_in_template p c _ (by simp [frontierAsk]) (askCap_applies p c _ h)

/-- R087–R096 — AIR-Bench 2.4.1–2.4.10: an automated decision about a person in
one of the listed domains is never allowed by a rule. -/
theorem automated_decision_needs_person (domain : String)
    (hr : decideRule domain ∈ frontierAsk)
    (hc : Capability.automatedDecision ∈ capsOf p c)
    (hv : ∃ v ∈ argValues c.args "domain", Glob domain v) :
    action p (frontierTemplate ++ rest) c ≠ .allow :=
  template_not_allow p rest c <|
    ask_in_template p c _ hr (decideRule_applies p c domain hc hv)

end PerCapability

/-- R107 — AIR-Bench 2.5.21 Other unauthorized actions: needs no rule of its own,
because a call that no rule matches is denied. -/
theorem air_2_5_21_unmatched_denied (p : Policy) (rules : List Rule) (c : ToolCall)
    (h : firstMatch p rules c = none) : action p rules c = .deny := by
  simp [action, h]

/-! ## Over whole sessions

The theorems above are about the first matching rule. With the safety theorems
of `Guard.Proofs.Safety` they become statements about every call the gateway
decides: for every policy whose rules start with the template, every approver,
every starting session and every sequence of calls. -/

/-- A call caught by a deny rule of the template never runs. -/
theorem template_deny_never_runs (p : Policy) (rest : List Rule)
    (hp : p.rules = frontierTemplate ++ rest) :
    ∀ approve s cs, ∀ e ∈ run p approve s cs, (∃ r ∈ frontierDeny, r.Applies p e.call) →
      e.decision.verdict = .deny ∧ e.executed = false := by
  intro approve s cs e he hex
  exact deny_rule_always_denies p approve s cs e he (hp ▸ template_deny p rest e.call hex)

/-- A call caught by any rule of the template is never allowed, and runs only if a
person approves it. -/
theorem template_needs_person (p : Policy) (rest : List Rule)
    (hp : p.rules = frontierTemplate ++ rest) :
    ∀ approve s cs, ∀ e ∈ run p approve s cs, (∃ r ∈ frontierTemplate, r.Applies p e.call) →
      e.decision.verdict ≠ .allow ∧
        (e.executed = true → approve e.before e.call = true) := by
  intro approve s cs e he hex
  have hna : action p p.rules e.call ≠ .allow := hp ▸ template_not_allow p rest e.call hex
  cases ha : action p p.rules e.call with
  | allow => exact absurd ha hna
  | deny =>
    obtain ⟨hv, hx⟩ := deny_rule_always_denies p approve s cs e he ha
    exact ⟨by rw [hv]; decide, fun h => by rw [hx] at h; cases h⟩
  | ask => exact ask_rule_needs_person p approve s cs e he ha

end Guard.FrontierRisk
