import Guard.Spec.Glob
import Guard.Impl.Glob

/-!
# The glob matcher agrees with the spec

`glob_correct : Impl.glob pat s = true ↔ Glob pat s`.

It also provides `Decidable (Glob pat s)` by running the proved matcher, which
is how the rule semantics (`Guard.Spec.Semantics`) evaluates patterns.
-/

namespace Guard

open Impl

theorem nullable_iff (p : List Tok) : nullable p = true ↔ Matches p [] := by
  induction p with
  | nil => exact ⟨fun _ => .nil, fun _ => rfl⟩
  | cons t p ih =>
    cases t with
    | lit c => exact ⟨fun h => by simp [nullable] at h, fun h => by cases h⟩
    | one => exact ⟨fun h => by simp [nullable] at h, fun h => by cases h⟩
    | star =>
      simp only [nullable]
      exact ⟨fun h => .starNone (ih.mp h), fun h => by cases h with | starNone h => exact ih.mpr h⟩
    | dstar =>
      simp only [nullable]
      exact ⟨fun h => .dstarNone (ih.mp h), fun h => by cases h with | dstarNone h => exact ih.mpr h⟩

theorem deriv_iff (d : Char) (s : List Char) (p : List Tok) :
    Matches p (d :: s) ↔ ∃ q ∈ deriv d p, Matches q s := by
  induction p with
  | nil => simp only [deriv, List.not_mem_nil, false_and, exists_false, iff_false]; intro h; cases h
  | cons t p ih =>
    cases t with
    | lit c =>
      by_cases hc : c = d
      · subst hc
        simp only [deriv, ite_true, List.mem_singleton, exists_eq_left]
        exact ⟨fun h => by cases h with | lit h => exact h, .lit⟩
      · simp only [deriv, hc, ite_false, List.not_mem_nil, false_and, exists_false, iff_false]
        intro h; cases h; exact hc rfl
    | one =>
      by_cases hd : d = '/'
      · simp only [deriv, hd, ne_eq, not_true_eq_false, ite_false, List.not_mem_nil, false_and,
          exists_false, iff_false]
        intro h; cases h with | one h _ => exact h rfl
      · simp only [deriv, ne_eq, hd, not_false_eq_true, ite_true, List.mem_singleton, exists_eq_left]
        exact ⟨fun h => by cases h with | one _ h => exact h, .one hd⟩
    | star =>
      constructor
      · intro h
        cases h with
        | starNone h =>
          obtain ⟨q, hq, hm⟩ := ih.mp h
          exact ⟨q, by simp only [deriv, List.mem_append]; exact Or.inr hq, hm⟩
        | starMore hd h =>
          exact ⟨.star :: p, by simp [deriv, hd], h⟩
      · rintro ⟨q, hq, hm⟩
        simp only [deriv, List.mem_append] at hq
        rcases hq with hq | hq
        · by_cases hd : d = '/'
          · simp [hd] at hq
          · simp only [ne_eq, hd, not_false_eq_true, ite_true, List.mem_singleton] at hq
            subst hq; exact .starMore hd hm
        · exact .starNone (ih.mpr ⟨q, hq, hm⟩)
    | dstar =>
      constructor
      · intro h
        cases h with
        | dstarNone h =>
          obtain ⟨q, hq, hm⟩ := ih.mp h
          exact ⟨q, List.mem_cons_of_mem _ hq, hm⟩
        | dstarMore h => exact ⟨.dstar :: p, List.mem_cons_self .., h⟩
      · rintro ⟨q, hq, hm⟩
        simp only [deriv, List.mem_cons] at hq
        rcases hq with rfl | hq
        · exact .dstarMore hm
        · exact .dstarNone (ih.mpr ⟨q, hq, hm⟩)

theorem run_iff (s : List Char) (S : List (List Tok)) :
    run S s = true ↔ ∃ p ∈ S, Matches p s := by
  induction s generalizing S with
  | nil =>
    simp only [run, List.any_eq_true]
    exact ⟨fun ⟨p, hp, h⟩ => ⟨p, hp, (nullable_iff p).mp h⟩,
           fun ⟨p, hp, h⟩ => ⟨p, hp, (nullable_iff p).mpr h⟩⟩
  | cons d s ih =>
    simp only [run, ih, List.mem_eraseDups, List.mem_flatMap]
    constructor
    · rintro ⟨q, ⟨p, hp, hq⟩, hm⟩
      exact ⟨p, hp, (deriv_iff d s p).mpr ⟨q, hq, hm⟩⟩
    · rintro ⟨p, hp, hm⟩
      obtain ⟨q, hq, hm⟩ := (deriv_iff d s p).mp hm
      exact ⟨q, ⟨p, hp, hq⟩, hm⟩

/-- **The glob matcher that runs agrees with the spec** (part of `impl_eq_spec`). -/
theorem glob_correct (pat s : String) : glob pat s = true ↔ Glob pat s := by
  simp [glob, Glob, run_iff]

instance (pat s : String) : Decidable (Glob pat s) :=
  decidable_of_iff _ (glob_correct pat s)

end Guard
