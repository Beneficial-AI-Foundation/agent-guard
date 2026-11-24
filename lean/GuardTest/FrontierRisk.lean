import Guard

/-!
The frontier-risk template (`Guard.Rulesets.FrontierRisk`) at the top of a rule
file whose last rule allows everything. The template still decides every call it
catches; everything else falls through to the catch-all.
-/

namespace GuardTest.FrontierRisk
open Guard Guard.FrontierRisk

def allowAll : Rule :=
  { tool := "**", conds := [], action := .allow, effect := .read,
    untrusted := false, highImpact := false }

def permissive : Policy := Policy.mk 1 [] (frontierTemplate ++ [allowAll])

def call (server tool : String) (args : Args := []) : ToolCall := ⟨server, tool, args⟩

def files (paths : List String) : Value :=
  .arr (paths.map fun p => .obj [("path", .str p), ("content", .str "…")])

/-- Verdicts of a whole session where the person approves every `ask`. -/
def verdicts (cs : List ToolCall) : List Verdict :=
  (run permissive (fun _ _ => true) {} cs).map (·.decision.verdict)

/-! Deny rules win over the catch-all allow. -/
#guard verdicts [
  call "scanner" "port_scan" [("target", .str "10.0.0.0/8")],
  call "scanner" "vuln_scan_host",
  call "nuclear" "set_rod_position",
  call "weapons" "arm",
  call "files" "push_files" [("files", files ["README.md", "agentguard/rules.yaml"])]
] == [.deny, .deny, .deny, .deny, .deny]

/-! Ask rules: sending and automated decisions in the listed domains need a person.
A decision with no `domain` counts as one of them (the safe direction). -/
#guard verdicts [
  call "mail" "send_email" [("to", .str "someone@example.com")],
  call "hr" "decide_candidate" [("domain", .str "employment")],
  call "bank" "decide_loan" [("domain", .str "financing_consumer")],
  call "hr" "decide_candidate"
] == [.ask, .ask, .ask, .ask]

/-! Everything the template doesn't catch is left to the rules after it. -/
#guard verdicts [
  call "files" "push_files" [("files", files ["README.md"])],
  call "hr" "decide_candidate" [("domain", .str "scheduling")],
  call "notes" "read_note"
] == [.allow, .allow, .allow]

end GuardTest.FrontierRisk
