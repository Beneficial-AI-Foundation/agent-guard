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
    firstMatch p.rules e.call = none →
      e.decision.verdict = .deny ∧ e.executed = false

/-- **If the first matching rule says deny, the call never runs.** -/
def DenyRuleAlwaysDenies : Prop :=
  ∀ p approve s cs, ∀ e ∈ run p approve s cs,
    action p.rules e.call = .deny →
      e.decision.verdict = .deny ∧ e.executed = false

/-- **If the first matching rule says ask, the call never runs without a person.** -/
def AskRuleNeedsPerson : Prop :=
  ∀ p approve s cs, ∀ e ∈ run p approve s cs,
    action p.rules e.call = .ask →
      e.decision.verdict ≠ .allow ∧
        (e.executed = true → approve e.before e.call = true)

/-- **Only an allow rule can allow.** -/
def AllowNeedsAllowRule : Prop :=
  ∀ p approve s cs, ∀ e ∈ run p approve s cs,
    e.decision.verdict = .allow → action p.rules e.call = .allow

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

/-- **A call sent to a person is already within the leak rules**, so approving it
can't leak data. -/
def ApprovalCannotLeak : Prop :=
  ∀ p approve s cs, ∀ e ∈ run p approve s cs,
    e.decision.verdict = .ask →
      ∀ d ∈ e.decision.cls.dests, e.before.level ≤ d

end Guard
