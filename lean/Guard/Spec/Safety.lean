import Guard.Spec.Session
import Guard.Impl.Glob

/-!
# Safety theorems (statements only)

Each property below is a `Prop`; `Guard.Proofs.Safety` proves every one of them.
They are stated for **every** policy `p`, **every** approver `approve` (the
person answering `ask`, who may say yes to anything), **every** starting session
`s` and **every** sequence of calls `cs`, so they hold however the agent is
tricked into choosing its calls.

`run p approve s cs` is the list of decided calls; `e.executed` says whether a
call actually ran. `List.Pairwise R l` means `R e₁ e₂` for every `e₁` that comes
**before** `e₂` in `l`.
-/

namespace Guard

/-- **The matcher that runs equals the spec.** Every other part of the decision
runs the spec's own definitions, so this is the whole of `Impl = Spec`. -/
def ImplEqSpec : Prop :=
  ∀ pat s : String, Impl.glob pat s = true ↔ Glob pat s

/-- **A call is executed only if it was allowed, or asked and approved.** -/
def ExecutedOnlyIfAllowed : Prop :=
  ∀ p approve s cs, ∀ e ∈ run p approve s cs,
    e.executed = true ↔
      (e.decision.verdict = .allow ∨
        (e.decision.verdict = .ask ∧ approve e.before e.call = true))

/-- **A call matching no rule is never executed.** -/
def UnmatchedDenied : Prop :=
  ∀ p approve s cs, ∀ e ∈ run p approve s cs,
    firstMatch p p.rules e.call = none →
      e.decision.verdict = .deny ∧ e.executed = false

/-- **If the first matching rule says deny, the call never runs.** -/
def DenyRuleAlwaysDenies : Prop :=
  ∀ p approve s cs, ∀ e ∈ run p approve s cs,
    action p p.rules e.call = .deny →
      e.decision.verdict = .deny ∧ e.executed = false

/-- **If the first matching rule says ask, the call never runs without a person.** -/
def AskRuleNeedsPerson : Prop :=
  ∀ p approve s cs, ∀ e ∈ run p approve s cs,
    action p p.rules e.call = .ask →
      e.decision.verdict ≠ .allow ∧
        (e.executed = true → approve e.before e.call = true)

/-- **Only an allow rule can allow.** -/
def AllowNeedsAllowRule : Prop :=
  ∀ p approve s cs, ∀ e ∈ run p approve s cs,
    e.decision.verdict = .allow → action p p.rules e.call = .allow

/-- **No exfiltration.** Nothing goes to a place below what was already read:
every call that isn't denied (so every call that runs, and every call shown to a
person) writes only to labels at least the starting level, and at least the
label of everything read by an earlier call that ran. -/
def NoExfiltration : Prop :=
  ∀ p approve s cs,
    (∀ e ∈ run p approve s cs, e.decision.verdict ≠ .deny →
      ∀ d ∈ e.decision.cls.dests, s.level ≤ d) ∧
    (run p approve s cs).Pairwise (fun e₁ e₂ =>
      e₁.executed = true → e₂.decision.verdict ≠ .deny →
        ∀ d ∈ e₂.decision.cls.dests, e₁.decision.cls.readLevel ≤ d)

/-- **The session level never goes down**, within a call or from one call to the next. -/
def LevelMonotone : Prop :=
  ∀ p approve s cs,
    (∀ e ∈ run p approve s cs, e.before.level ≤ e.after.level) ∧
    (run p approve s cs).Pairwise (fun e₁ e₂ => e₁.after.level ≤ e₂.before.level)

/-- **No untrusted steering.** After outsider text has been read (before the
session started, or by an earlier call that ran), no high-impact call is allowed
without a person. -/
def NoUntrustedSteering : Prop :=
  ∀ p approve s cs,
    (s.tainted = true → ∀ e ∈ run p approve s cs,
      e.decision.cls.highImpact = true → e.decision.verdict ≠ .allow) ∧
    (run p approve s cs).Pairwise (fun e₁ e₂ =>
      e₁.executed = true → e₁.decision.cls.untrusted = true →
        e₂.decision.cls.highImpact = true → e₂.decision.verdict ≠ .allow)

/-! ## Resources

`NoExfiltration` is about the labels a call reads and writes; `resources` is
what decides those labels. These three say the slot behaves. -/

/-- **A policy that lists no servers behaves exactly as before.** The migration
statement: every rule file written today keeps its meaning. -/
def ResourceDefaultIsRepo : Prop :=
  ∀ p c, p.servers = [] →
    knownLabel p c = (repoOf c.args).bind (repoLabel p)

/-- **A flat server has exactly its declared label**, whatever the call's
arguments are: nothing it reads pushes the session above `l`, and it can be
written to from any session at or below `l`. This is what stops a second
connection from poisoning the session on its first read. -/
def FlatServerLabel : Prop :=
  ∀ p c l, serverResource p c = some (.flat l) →
    readLabel p c = l ∧ writeLabel p c = l

/-- **An unnameable resource still counts in the safe direction.** Reading it
is treated as the highest label and writing to it as the lowest, so a server
the policy says nothing about can never be used to launder data. -/
def UnknownResourceIsSafe : Prop :=
  ∀ p c, knownLabel p c = none →
    readLabel p c = p.top ∧ writeLabel p c = 0

/-! ## Capabilities

A rule may select on a **capability** rather than a tool name. These say the
selection is scoped: a capability rule reaches only the tools a connection
declared for it, and a rule that names no capability behaves as it does today. -/

/-- **A capability rule needs a declaration.** It never applies to a call whose
server did not declare that capability for that tool — so pasting
`capability: send_message, action: ask` at the top of a rule file cannot reach
a server that never said it sends anything. -/
def CapabilityNeedsDeclaration : Prop :=
  ∀ (p : Policy) (r : Rule) (c : ToolCall) (cp : Capability),
    r.cap = some cp → cp ∉ capsOf p c → ¬ r.Applies p c

/-- **An unlisted server has no capabilities**, so no capability rule fires for
it and its calls fall through to the rules selected by name — and, failing
those, to deny. -/
def UnlistedServerHasNoCaps : Prop :=
  ∀ p c, serverOf p c = none → capsOf p c = []

/-- **Rules selected by name are unchanged.** A rule with no `capability` applies
exactly when its tool pattern and conditions say so, as every rule does today. -/
def NameRulesUnchanged : Prop :=
  ∀ (p : Policy) (r : Rule) (c : ToolCall), r.cap = none →
    (r.Applies p c ↔ Glob r.tool c.name ∧ ∀ cd ∈ r.conds, cd.Holds r.action c.args)

/-- **A call sent to a person is already within the leak rules**, so approving it
can't leak data. -/
def ApprovalCannotLeak : Prop :=
  ∀ p approve s cs, ∀ e ∈ run p approve s cs,
    e.decision.verdict = .ask →
      ∀ d ∈ e.decision.cls.dests, e.before.level ≤ d

end Guard
