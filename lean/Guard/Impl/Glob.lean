import Guard.Spec.Glob

/-!
# Glob matcher (implementation)

Runs a pattern against a string by keeping the set of pattern suffixes that can
still match what remains of the string (an NFA simulation using pattern
derivatives). The set never holds more than one copy of each suffix, so the cost
is at most (string length) × (pattern length)² comparisons, with no backtracking
blow-up whatever the input.

`Guard.Proofs.Glob.glob_correct` proves `glob pat s = true ↔ Glob pat s`.
-/

namespace Guard.Impl

/-- The suffix matches the empty string (it is all stars). -/
def nullable : List Tok → Bool
  | [] => true
  | .star :: p => nullable p
  | .dstar :: p => nullable p
  | _ => false

/-- The suffixes left after the pattern `p` consumes the character `d`. -/
def deriv (d : Char) : List Tok → List (List Tok)
  | [] => []
  | .lit c :: p => if c = d then [p] else []
  | .one :: p => if d ≠ '/' then [p] else []
  | .star :: p => (if d ≠ '/' then [.star :: p] else []) ++ deriv d p
  | .dstar :: p => (.dstar :: p) :: deriv d p

/-- Runs the set of live suffixes `S` over the remaining characters. -/
def run : List (List Tok) → List Char → Bool
  | S, [] => S.any nullable
  | S, d :: s => run (S.flatMap (deriv d)).eraseDups s

def glob (pat s : String) : Bool :=
  run [tokenize pat.toList] s.toList

end Guard.Impl
