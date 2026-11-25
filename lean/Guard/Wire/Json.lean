import Lean.Data.Json
import Guard.Spec.Session

/-!
# JSON in and out

Turns JSON into the spec's types (`Value`, `ToolCall`, `Session`) and decisions
back into JSON. This layer is **trusted, not proved** (it is listed in
`docs/threat-model.md`): it only reshapes data, and any error here makes the
gateway deny the call.

Duplicate keys in a JSON object: the last one wins (Lean's parser, like Python's
`json`), and the gateway sends Lean exactly the arguments it forwards.
-/

namespace Guard.Wire

open Lean

/-- JSON → `Value`. Numbers and booleans become their JSON text. -/
partial def toValue : Json → Value
  | .null => .null
  | .bool b => .str (toString b)
  | .num n => .str n.toString
  | .str s => .str s
  | .arr xs => .arr (xs.toList.map toValue)
  | .obj kvs => .obj (kvs.toList.map fun (k, v) => (k, toValue v))

def objFields (j : Json) (what : String) : Except String (List (String × Json)) :=
  match j with
  | .obj kvs => pure kvs.toList
  | _ => throw s!"{what} must be a JSON object"

/-- Rejects keys outside `allowed`, so a typo can't silently drop a field. -/
def checkKeys (j : Json) (what : String) (allowed : List String) : Except String Unit := do
  for (k, _) in ← objFields j what do
    unless allowed.contains k do
      throw s!"{what}: unknown key \"{k}\" (allowed: {", ".intercalate allowed})"

def getStr (j : Json) (k : String) (what : String) : Except String String :=
  match j.getObjVal? k with
  | .ok (.str s) => pure s
  | .ok _ => throw s!"{what}.{k} must be a string"
  | .error _ => throw s!"{what}.{k} is missing"

def decodeCall (j : Json) : Except String ToolCall := do
  checkKeys j "call" ["server", "tool", "arguments"]
  let server ← getStr j "server" "call"
  let tool ← getStr j "tool" "call"
  let args ← match j.getObjVal? "arguments" with
    | .ok a@(.obj _) => (objFields a "call.arguments").map (·.map fun (k, v) => (k, toValue v))
    | .ok .null | .error _ => pure []
    | .ok _ => throw "call.arguments must be a JSON object"
  pure { server, tool, args }

def decodeSession (p : Policy) (j : Json) : Except String Session := do
  checkKeys j "session" ["level", "tainted"]
  let level ← match j.getObjVal? "level" with
    | .ok v => v.getNat?.mapError (fun _ => "session.level must be a natural number")
    | .error _ => pure 0
  let tainted ← match j.getObjVal? "tainted" with
    | .ok v => v.getBool?.mapError (fun _ => "session.tainted must be true or false")
    | .error _ => pure false
  unless level < p.labelCount do
    throw s!"session.level {level} is out of range (the policy has {p.labelCount} labels)"
  pure { level, tainted }

def encodeSession (s : Session) : Json :=
  Json.mkObj [("level", toJson s.level), ("tainted", toJson s.tainted)]

def verdictName : Verdict → String
  | .allow => "allow"
  | .ask => "ask"
  | .deny => "deny"

def causeName : Cause → String
  | .rule => "rule"
  | .noRule => "no_rule"
  | .leak => "leak"
  | .untrusted => "untrusted"
  | .stopped => "stopped"
  | .allowed => "allowed"

/-- The theorem that guarantees this verdict holds. -/
def theoremFor (d : Decision) : String :=
  match d.verdict, d.cause with
  | .deny, .rule => "deny_rule_always_denies"
  | .deny, .noRule => "unmatched_denied"
  | .deny, .leak => "no_exfiltration"
  | .ask, .untrusted => "no_untrusted_steering"
  | .deny, .stopped => "kill_switch"
  | .ask, _ => "ask_rule_needs_person"
  | _, _ => "allow_needs_allow_rule"

def encodeDecision (d : Decision) : List (String × Json) :=
  [ ("verdict", Json.str (verdictName d.verdict)),
    ("cause", Json.str (causeName d.cause)),
    -- 1-based, as people count rules in the file
    ("rule", match d.cls.rule with | some (i, _) => toJson (i + 1) | none => Json.null),
    ("theorem", Json.str (theoremFor d)),
    ("next", encodeSession d.next),
    ("class", Json.mkObj [
      ("readLevel", toJson d.cls.readLevel),
      ("dests", toJson d.cls.dests),
      ("untrusted", toJson d.cls.untrusted),
      ("highImpact", toJson d.cls.highImpact)]) ]

end Guard.Wire
