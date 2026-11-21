import Guard.Wire.Json

/-!
# Rule-file validation

Turns the JSON form of `rules.yaml` into a `Policy`, or a list of every problem
found. A rule file with any problem is never loaded (the previous rules stay in
force). Unknown keys are errors, so a typo such as `whne:` can't silently drop a
condition.

```json
{ "labels": ["public", "private"],
  "repos":  [{ "match": "*/demo-private", "label": "private" }],
  "rules":  [{ "tool": "github.push_files", "when": { "branch": ["main", "master"] },
               "action": "deny", "effect": "write", "source": "trusted", "impact": "high" }] }
```

Omitted rule attributes take their safe values: `effect: readwrite`,
`source: untrusted`, `impact: high`.
-/

namespace Guard.Wire

open Lean

/-- Runs `x`, recording its error instead of stopping. -/
def collect {α} (errs : Array String) (x : Except String α) : Option α × Array String :=
  match x with
  | .ok a => (some a, errs)
  | .error e => (none, errs.push e)

def decodePats (what : String) : Json → Except String (List String)
  | .str s => if s.isEmpty then throw s!"{what}: empty pattern" else pure [s]
  | .arr xs => do
    if xs.isEmpty then throw s!"{what}: needs at least one pattern"
    xs.toList.mapM fun
      | .str s => if s.isEmpty then throw s!"{what}: empty pattern" else pure s
      | _ => throw s!"{what}: patterns must be strings"
  | _ => throw s!"{what}: must be a pattern or a list of patterns"

def decodeEnum {α} (j : Json) (k what : String) (dflt : α) (opts : List (String × α)) :
    Except String α :=
  match j.getObjVal? k with
  | .error _ => pure dflt
  | .ok (.str s) =>
    match opts.lookup s with
    | some a => pure a
    | none => throw s!"{what}.{k}: \"{s}\" is not one of {", ".intercalate (opts.map (·.1))}"
  | .ok _ => throw s!"{what}.{k} must be a string"

def decodeRule (i : Nat) (j : Json) : Except String Rule := do
  let what := s!"rules[{i + 1}]"
  checkKeys j what ["tool", "when", "action", "effect", "source", "impact", "note"]
  let tool ← getStr j "tool" what
  if tool.isEmpty then throw s!"{what}.tool: empty pattern"
  if (j.getObjVal? "action").toOption.isNone then
    throw s!"{what}.action is missing (allow, ask or deny)"
  let action ← decodeEnum j "action" what Action.deny
    [("allow", .allow), ("ask", .ask), ("deny", .deny)]
  let effect ← decodeEnum j "effect" what Effect.readwrite
    [("read", .read), ("write", .write), ("readwrite", .readwrite)]
  let untrusted ← decodeEnum j "source" what true [("trusted", false), ("untrusted", true)]
  let highImpact ← decodeEnum j "impact" what true [("low", false), ("high", true)]
  let conds ← match j.getObjVal? "when" with
    | .error _ | .ok .null => pure []
    | .ok w => do
      let kvs ← objFields w s!"{what}.when"
      kvs.mapM fun (k, v) => do
        if k.isEmpty then throw s!"{what}.when: empty argument name"
        pure { key := k, pats := ← decodePats s!"{what}.when.{k}" v : Cond }
  pure { tool, conds, action, effect, untrusted, highImpact }

def decodeLabels (j : Json) : Except String (List String) := do
  let xs ← match j.getObjVal? "labels" with
    | .ok (.arr xs) => pure xs.toList
    | .ok _ => throw "labels must be a list of names, lowest first"
    | .error _ => throw "labels is missing (e.g. [public, private])"
  if xs.isEmpty then throw "labels: needs at least one label"
  let names ← xs.mapM fun
    | .str s => if s.isEmpty then throw "labels: empty name" else pure s
    | _ => throw "labels: names must be strings"
  if names.eraseDups.length != names.length then throw "labels: names must be different"
  pure names

def decodeRepo (labels : List String) (i : Nat) (j : Json) : Except String RepoLabel := do
  let what := s!"repos[{i + 1}]"
  checkKeys j what ["match", "label", "note"]
  let pat ← getStr j "match" what
  if pat.isEmpty then throw s!"{what}.match: empty pattern"
  let name ← getStr j "label" what
  match labels.idxOf? name with
  | some l => pure { pat, label := l }
  | none => throw s!"{what}.label: \"{name}\" is not in labels {labels}"

/-- The whole rule file, or every problem found in it. -/
def decodePolicy (j : Json) : Except (List String) Policy := Id.run do
  let mut errs : Array String := #[]
  if let .error e := checkKeys j "rule file" ["labels", "repos", "rules", "version"] then
    errs := errs.push e
  let (labels?, errs') := collect errs (decodeLabels j)
  errs := errs'
  let labels := labels?.getD []
  let mut repos : Array RepoLabel := #[]
  match j.getObjVal? "repos" with
  | .error _ | .ok .null => pure ()
  | .ok (.arr xs) =>
    for h : i in [0:xs.size] do
      if labels?.isSome then
        let (r?, errs') := collect errs (decodeRepo labels i xs[i])
        errs := errs'
        if let some r := r? then repos := repos.push r
  | .ok _ => errs := errs.push "repos must be a list"
  let mut rules : Array Rule := #[]
  match j.getObjVal? "rules" with
  | .ok (.arr xs) =>
    for h : i in [0:xs.size] do
      let (r?, errs') := collect errs (decodeRule i xs[i])
      errs := errs'
      if let some r := r? then rules := rules.push r
  | .ok _ => errs := errs.push "rules must be a list"
  | .error _ => errs := errs.push "rules is missing"
  if errs.isEmpty then
    return .ok { labelCount := labels.length, repos := repos.toList, rules := rules.toList }
  else
    return .error errs.toList

end Guard.Wire
