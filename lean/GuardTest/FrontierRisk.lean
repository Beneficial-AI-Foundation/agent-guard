import Guard

/-!
The frontier-risk template (`Guard.Rulesets.FrontierRisk`) at the top of a rule
file whose last rule allows everything. The template still decides every call
it catches; everything else falls through to the catch-all.

Each server declares what its tools do. That declaration is the whole of the
template's reach: a server that declares nothing is never caught by it.
-/

namespace GuardTest.FrontierRisk
open Guard Guard.FrontierRisk

def allowAll : Rule :=
  { tool := "**", conds := [], action := .allow, effect := .read,
    untrusted := false, highImpact := false }

def servers : List Server :=
  [ { name := "scanner", caps := [⟨.networkScan, ["port_scan", "vuln_scan*"]⟩] },
    { name := "plant",   caps := [⟨.operatePhysicalSystem, ["*"]⟩] },
    { name := "files",   caps := [⟨.writeData, ["push_files"]⟩] },
    { name := "mail",    caps := [⟨.sendMessage, ["send_*"]⟩] },
    { name := "hr",      caps := [⟨.automatedDecision, ["decide_*"]⟩] },
    { name := "notes",   caps := [] } ]

def permissive : Policy :=
  { labelCount := 1, repos := [], servers, rules := frontierTemplate ++ [allowAll] }

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
  call "plant" "set_rod_position",
  call "plant" "arm",
  call "files" "push_files" [("files", files ["README.md", ".agentguard/rules.yaml"])]
] == [.deny, .deny, .deny, .deny, .deny]

/-! Ask rules: sending and automated decisions in the listed domains need a person.
A decision with no `domain` counts as one of them (the safe direction). -/
#guard verdicts [
  call "mail" "send_email" [("to", .str "someone@example.com")],
  call "hr" "decide_candidate" [("domain", .str "employment")],
  call "hr" "decide_loan" [("domain", .str "financing_consumer")],
  call "hr" "decide_candidate"
] == [.ask, .ask, .ask, .ask]

/-! Everything the template doesn't catch is left to the rules after it. -/
#guard verdicts [
  call "files" "push_files" [("files", files ["README.md"])],
  call "hr" "decide_candidate" [("domain", .str "scheduling")],
  call "notes" "read_note"
] == [.allow, .allow, .allow]

/-! **The template reaches only what a connection declared.** `notes` declares
nothing, so a tool whose name looks like a send is not caught — it falls through
to the rules after the template, exactly as if the template were absent. That is
`capability_needs_declaration`: pasting the template at the top cannot change
what an undeclared server may do. -/
#guard capsOf permissive (call "notes" "send_digest") == []
#guard verdicts [call "notes" "send_digest"] == [.allow]

/-! And `scanner.port_scan` is caught on its capability, not on its name: the
same tool on a server that declared nothing would not be. -/
#guard capsOf permissive (call "scanner" "port_scan") == [.networkScan]

end GuardTest.FrontierRisk
