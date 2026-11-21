import Guard.Spec.Rules
import Guard.Spec.Glob
import Guard.Proofs.Glob

/-!
# What a rule means

* A rule **applies** to a call when its tool pattern matches the call's name
  (`github.push_files`) and every one of its conditions holds.
* The rules are tried in order. **The first rule that applies decides**; if none
  applies, the answer is **deny**.

## Conditions

A condition `branch: [main, master]` looks at **every value of that key anywhere
in the arguments**: `path` finds the top-level `path` of `create_or_update_file`
and also every `files[].path` of `push_files`. Values are strings; numbers and
booleans are compared as their JSON text.

How a condition counts depends on the rule's action, always in the safe direction:

| Rule action    | Condition holds when …                                   |
|----------------|----------------------------------------------------------|
| `deny`, `ask`  | the key is **missing**, or **any** value matches         |
| `allow`        | the key is present and **every** value matches           |

So a call with several files is denied or paused if *one* file hits a deny/ask
rule, and only allowed by a conditional allow rule if *all* of them qualify. A
missing `branch` (which GitHub reads as "the default branch") counts as `main`
for a deny rule.

(Glob patterns are evaluated by the matcher proved equal to `Glob` in
`Guard.Proofs.Glob`; that is where the `Decidable` instance comes from.)
-/

namespace Guard

/-! ## Looking up argument values -/

mutual
/-- Every string inside a value. -/
def Value.leaves : Value → List String
  | .str s => [s]
  | .null => []
  | .arr xs => leavesList xs
  | .obj kvs => leavesObj kvs

def leavesList : List Value → List String
  | [] => []
  | v :: vs => v.leaves ++ leavesList vs

def leavesObj : List (String × Value) → List String
  | [] => []
  | (_, v) :: kvs => v.leaves ++ leavesObj kvs
end

mutual
/-- Every string stored under `key`, at any depth inside a value. -/
def Value.valuesAt (key : String) : Value → List String
  | .str _ => []
  | .null => []
  | .arr xs => valuesAtList key xs
  | .obj kvs => valuesAtObj key kvs

def valuesAtList (key : String) : List Value → List String
  | [] => []
  | v :: vs => v.valuesAt key ++ valuesAtList key vs

def valuesAtObj (key : String) : List (String × Value) → List String
  | [] => []
  | (k, v) :: kvs =>
    (if k = key then v.leaves else []) ++ v.valuesAt key ++ valuesAtObj key kvs
end

/-- Every value of `key` anywhere in the arguments. -/
def argValues (args : Args) (key : String) : List String :=
  valuesAtObj key args

/-! ## Conditions and rules -/

/-- The value matches one of the condition's patterns. -/
def Cond.Accepts (cd : Cond) (v : String) : Prop :=
  ∃ q ∈ cd.pats, Glob q v

/-- For deny and ask rules: the key is missing, or some value matches. -/
def Cond.MayHold (cd : Cond) (args : Args) : Prop :=
  argValues args cd.key = [] ∨ ∃ v ∈ argValues args cd.key, cd.Accepts v

/-- For allow rules: the key is present and every value matches. -/
def Cond.MustHold (cd : Cond) (args : Args) : Prop :=
  argValues args cd.key ≠ [] ∧ ∀ v ∈ argValues args cd.key, cd.Accepts v

def Cond.Holds (a : Action) (cd : Cond) (args : Args) : Prop :=
  if a = .allow then cd.MustHold args else cd.MayHold args

/-- The rule applies to the call. -/
def Rule.Applies (r : Rule) (c : ToolCall) : Prop :=
  Glob r.tool c.name ∧ ∀ cd ∈ r.conds, cd.Holds r.action c.args

/-! These instances let the definitions above run as they are. -/

instance (cd : Cond) (v : String) : Decidable (cd.Accepts v) :=
  inferInstanceAs (Decidable (∃ q ∈ cd.pats, Glob q v))

instance (cd : Cond) (args : Args) : Decidable (cd.MayHold args) :=
  inferInstanceAs (Decidable (_ ∨ _))

instance (cd : Cond) (args : Args) : Decidable (cd.MustHold args) :=
  inferInstanceAs (Decidable (_ ∧ _))

instance (a : Action) (cd : Cond) (args : Args) : Decidable (cd.Holds a args) :=
  inferInstanceAs (Decidable (if a = .allow then _ else _))

instance (r : Rule) (c : ToolCall) : Decidable (r.Applies c) :=
  inferInstanceAs (Decidable (_ ∧ _))

/-! ## First match wins -/

/-- The first rule (with its 0-based position) that applies, if any. -/
def firstMatchFrom (c : ToolCall) : Nat → List Rule → Option (Nat × Rule)
  | _, [] => none
  | i, r :: rs => if r.Applies c then some (i, r) else firstMatchFrom c (i + 1) rs

def firstMatch (rules : List Rule) (c : ToolCall) : Option (Nat × Rule) :=
  firstMatchFrom c 0 rules

/-- What the rules say about a call: the first applying rule's action, or deny. -/
def action (rules : List Rule) (c : ToolCall) : Action :=
  match firstMatch rules c with
  | some (_, r) => r.action
  | none => .deny

end Guard
