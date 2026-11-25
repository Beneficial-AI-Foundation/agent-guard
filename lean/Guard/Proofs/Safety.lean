import Guard.Spec.Safety
import Guard.Proofs.Glob

/-!
# Proofs of the safety theorems

Every property stated in `Guard.Spec.Safety` is proved here. The proofs go in
three layers:

1. facts about a single `step` (what each verdict implies);
2. facts about every event of a `run` (it was decided by `step`, and the session
   only ever grows);
3. the theorems themselves, which combine the two.
-/

namespace Guard

variable {p : Policy} {s : Session} {c : ToolCall}

/-! ## 1. One step -/

theorem classify_action (p : Policy) (c : ToolCall) :
    (classify p c).action = action p p.rules c := by
  unfold classify action
  split <;> simp_all

theorem classify_none (h : firstMatch p p.rules c = none) : (classify p c).action = .deny := by
  simp [classify_action, action, h]

/-- Everything the safety proofs need to know about one `step`. -/
theorem step_facts (p : Policy) (s : Session) (c : ToolCall) :
    (step p s c).cls = classify p c ∧
    ((classify p c).action = .deny → (step p s c).verdict = .deny) ∧
    ((step p s c).verdict ≠ .deny →
      (∀ d ∈ (classify p c).dests, s.level ≤ d) ∧
      (step p s c).next = s.absorb (classify p c)) ∧
    ((step p s c).verdict = .allow →
      (classify p c).action = .allow ∧ (s.tainted = true → (classify p c).highImpact = false)) := by
  simp only [step]
  repeat' split
  all_goals
    simp only [List.any_eq_true, decide_eq_true_eq, not_exists, not_and, Nat.not_lt,
      Bool.and_eq_true] at *
    refine ⟨?_, ?_, ?_, ?_⟩ <;> (try intros) <;> simp_all
  all_goals
    rename_i h _
    cases hk : (classify p c).action <;> simp_all

theorem step_cls : (step p s c).cls = classify p c := (step_facts p s c).1

theorem step_deny_of_action (h : (classify p c).action = .deny) :
    (step p s c).verdict = .deny := (step_facts p s c).2.1 h

theorem step_dests (h : (step p s c).verdict ≠ .deny) :
    ∀ d ∈ (classify p c).dests, s.level ≤ d := ((step_facts p s c).2.2.1 h).1

theorem step_next (h : (step p s c).verdict ≠ .deny) :
    (step p s c).next = s.absorb (classify p c) := ((step_facts p s c).2.2.1 h).2

theorem step_allow (h : (step p s c).verdict = .allow) :
    (classify p c).action = .allow ∧ (s.tainted = true → (classify p c).highImpact = false) :=
  (step_facts p s c).2.2.2 h

theorem step_ask_not_allow (h : (classify p c).action = .ask) : (step p s c).verdict ≠ .allow := by
  intro ha
  have := (step_allow ha).1
  simp_all

theorem runs_not_deny {v : Verdict} {b : Bool} (h : runs v b = true) : v ≠ .deny := by
  cases v <;> simp_all [runs]

/-- After a call: the session never shrinks, and if the call ran it absorbed what was read. -/
theorem after_facts (p : Policy) (s : Session) (c : ToolCall) (b : Bool) :
    let s' := if runs (step p s c).verdict b then (step p s c).next else s
    s.level ≤ s'.level ∧ (s.tainted = true → s'.tainted = true) ∧
    (runs (step p s c).verdict b = true →
      (classify p c).readLevel ≤ s'.level ∧
      ((classify p c).untrusted = true → s'.tainted = true)) := by
  intro s'
  by_cases hr : runs (step p s c).verdict b = true
  · have hn := step_next (runs_not_deny hr)
    simp only [s', hr, ite_true, hn, Session.absorb]
    refine ⟨Nat.le_max_left _ _, fun ht => by simp [ht], fun _ => ⟨Nat.le_max_right _ _, ?_⟩⟩
    intro hu; simp [hu]
  · simp only [s', hr, ite_false, Bool.false_eq_true]
    exact ⟨Nat.le_refl _, id, fun h => h.elim⟩

/-! ## 2. Every event of a run -/

theorem run_cons (p : Policy) (a : Session → ToolCall → Bool) (s : Session) (c : ToolCall)
    (cs : List ToolCall) :
    run p a s (c :: cs) =
      { call := c, before := s, decision := step p s c,
        executed := runs (step p s c).verdict (a s c),
        after := if runs (step p s c).verdict (a s c) then (step p s c).next else s } ::
      run p a (if runs (step p s c).verdict (a s c) then (step p s c).next else s) cs := rfl

/-- Every event was decided by `step` from the session before it, ran exactly when
`runs` says so, and started from a session at least as high as the run's start. -/
theorem run_facts (p : Policy) (a : Session → ToolCall → Bool) :
    ∀ (cs : List ToolCall) (s : Session), ∀ e ∈ run p a s cs,
      e.decision = step p e.before e.call ∧
      e.executed = runs e.decision.verdict (a e.before e.call) ∧
      e.after = (if e.executed then e.decision.next else e.before) ∧
      s.level ≤ e.before.level ∧ (s.tainted = true → e.before.tainted = true)
  | [], _, e, he => by simp [run] at he
  | c :: cs, s, e, he => by
    rw [run_cons, List.mem_cons] at he
    rcases he with rfl | he
    · exact ⟨rfl, rfl, rfl, Nat.le_refl _, id⟩
    · obtain ⟨h1, h2, h3, h4, h5⟩ := run_facts p a cs _ e he
      obtain ⟨g1, g2, -⟩ := after_facts p s c (a s c)
      exact ⟨h1, h2, h3, Nat.le_trans g1 h4, fun ht => h5 (g2 ht)⟩

/-! ## 3. The theorems -/

theorem impl_eq_spec : ImplEqSpec := glob_correct

theorem executed_only_if_allowed : ExecutedOnlyIfAllowed := by
  intro p a s cs e he
  obtain ⟨-, hx, -⟩ := run_facts p a cs s e he
  rw [hx]
  cases e.decision.verdict <;> simp [runs]

theorem unmatched_denied : UnmatchedDenied := by
  intro p a s cs e he hm
  obtain ⟨hd, hx, -⟩ := run_facts p a cs s e he
  have hv : e.decision.verdict = .deny := by rw [hd]; exact step_deny_of_action (classify_none hm)
  exact ⟨hv, by rw [hx, hv]; rfl⟩

theorem deny_rule_always_denies : DenyRuleAlwaysDenies := by
  intro p a s cs e he hm
  obtain ⟨hd, hx, -⟩ := run_facts p a cs s e he
  have hv : e.decision.verdict = .deny := by
    rw [hd]; exact step_deny_of_action (by rw [classify_action]; exact hm)
  exact ⟨hv, by rw [hx, hv]; rfl⟩

theorem ask_rule_needs_person : AskRuleNeedsPerson := by
  intro p a s cs e he hm
  obtain ⟨hd, hx, -⟩ := run_facts p a cs s e he
  have hna : e.decision.verdict ≠ .allow := by
    rw [hd]; exact step_ask_not_allow (by rw [classify_action]; exact hm)
  refine ⟨hna, fun hex => ?_⟩
  rw [hx] at hex
  cases hv : e.decision.verdict <;> simp_all [runs]

theorem allow_needs_allow_rule : AllowNeedsAllowRule := by
  intro p a s cs e he hv
  obtain ⟨hd, -⟩ := run_facts p a cs s e he
  rw [hd] at hv
  rw [← classify_action]
  exact (step_allow hv).1

/-! ### Capabilities -/

theorem capability_needs_declaration : CapabilityNeedsDeclaration := by
  intro p r c cp hcap hnot ha
  exact hnot (by simpa [Rule.CapHolds, hcap] using ha.2.1)

theorem unlisted_server_has_no_caps : UnlistedServerHasNoCaps := by
  intro p c h
  simp [capsOf, h]

theorem name_rules_unchanged : NameRulesUnchanged := by
  intro p r c h
  simp [Rule.Applies, Rule.CapHolds, h]

/-! ### Resources -/

theorem resource_default_is_repo : ResourceDefaultIsRepo := by
  intro p c h
  simp [knownLabel, serverResource, serverOf, h]

theorem flat_server_label : FlatServerLabel := by
  intro p c l h
  simp [readLabel, writeLabel, knownLabel, h]

theorem unknown_resource_is_safe : UnknownResourceIsSafe := by
  intro p c h
  simp [readLabel, writeLabel, h]

theorem approval_cannot_leak : ApprovalCannotLeak := by
  intro p a s cs e he hv d hdst
  obtain ⟨hd, -⟩ := run_facts p a cs s e he
  rw [hd] at hv hdst
  rw [step_cls] at hdst
  exact step_dests (by rw [hv]; decide) d hdst

theorem level_monotone : LevelMonotone := by
  intro p a s cs
  constructor
  · intro e he
    obtain ⟨-, -, haft, -⟩ := run_facts p a cs s e he
    rw [haft]
    split
    · rename_i hex
      obtain ⟨hd, hx, -⟩ := run_facts p a cs s e he
      have hnd : e.decision.verdict ≠ .deny := by
        rw [hx] at hex; exact runs_not_deny hex
      rw [hd] at hnd ⊢
      rw [step_next hnd]
      exact Nat.le_max_left _ _
    · exact Nat.le_refl _
  · induction cs generalizing s with
    | nil => exact List.Pairwise.nil
    | cons c cs ih =>
      rw [run_cons]
      refine List.Pairwise.cons (fun e he => ?_) (ih _)
      exact (run_facts p a cs _ e he).2.2.2.1

theorem no_exfiltration : NoExfiltration := by
  intro p a s cs
  constructor
  · intro e he hnd d hdst
    obtain ⟨hd, -, -, hle, -⟩ := run_facts p a cs s e he
    rw [hd] at hnd hdst
    rw [step_cls] at hdst
    exact Nat.le_trans hle (step_dests hnd d hdst)
  · induction cs generalizing s with
    | nil => exact List.Pairwise.nil
    | cons c cs ih =>
      rw [run_cons]
      refine List.Pairwise.cons (fun e he hex hnd d hdst => ?_) (ih _)
      obtain ⟨hd, -, -, hle, -⟩ := run_facts p a cs _ e he
      obtain ⟨-, -, hread⟩ := after_facts p s c (a s c)
      have h1 := (hread hex).1
      rw [hd] at hnd hdst
      rw [step_cls] at hdst
      simp only [step_cls]
      exact Nat.le_trans h1 (Nat.le_trans hle (step_dests hnd d hdst))

theorem no_untrusted_steering : NoUntrustedSteering := by
  intro p a s cs
  constructor
  · intro ht e he hhi hv
    obtain ⟨hd, -, -, -, hte⟩ := run_facts p a cs s e he
    rw [hd] at hv hhi
    rw [step_cls] at hhi
    have := (step_allow hv).2 (hte ht)
    simp_all
  · induction cs generalizing s with
    | nil => exact List.Pairwise.nil
    | cons c cs ih =>
      rw [run_cons]
      refine List.Pairwise.cons (fun e he hex hu hhi hv => ?_) (ih _)
      obtain ⟨hd, -, -, -, hte⟩ := run_facts p a cs _ e he
      obtain ⟨-, -, hread⟩ := after_facts p s c (a s c)
      simp only [step_cls] at hu
      have ht := (hread hex).2 hu
      rw [hd] at hv hhi
      rw [step_cls] at hhi
      have := (step_allow hv).2 (hte ht)
      simp_all

end Guard
