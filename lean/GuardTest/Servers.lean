import Guard

/-!
The `servers` block, on the two-connection profile that motivates it: a code
host whose resource is `owner/repo`, and a mail server with no per-call
resource at all. A connection that declares nothing names no resource, so
everything it reads counts as the highest label. Second half: a capability rule
reaches only the tools a connection declared for it.
-/

namespace GuardTest.Servers
open Guard

def rd (tool : String) : Rule :=
  { tool, conds := [], action := .allow, effect := .read,
    untrusted := false, highImpact := false }

def wr (tool : String) : Rule :=
  { tool, conds := [], action := .allow, effect := .write,
    untrusted := false, highImpact := false }

def demoResources : List ResourceLabel := [⟨"*/demo-public", 0⟩, ⟨"*/demo-private", 1⟩]

def demoRules : List Rule :=
  [rd "github.get_file_contents", wr "github.push_files", rd "mail.read_inbox"]

/-- A profile whose connections declare nothing. -/
def undeclared : Policy :=
  { labelCount := 2, resources := demoResources, rules := demoRules }

/-- The same profile, with each server saying how it names a resource and what
its tools do. -/
def declared : Policy :=
  { labelCount := 2, resources := demoResources, rules := demoRules,
    servers := [
      { name := "github", resource := some (.keys ["owner", "repo"]),
        caps := [⟨.writeData, ["push_files"]⟩, ⟨.sendMessage, ["add_issue_comment"]⟩] },
      { name := "mail", resource := some (.flat 0),
        caps := [⟨.sendMessage, ["send_*"]⟩] }] }

def readMail : ToolCall := ⟨"mail", "read_inbox", [("folder", .str "INBOX")]⟩

def pushPublic : ToolCall :=
  ⟨"github", "push_files", [("owner", .str "Acme"), ("repo", .str "demo-public")]⟩

def verdicts (p : Policy) (cs : List ToolCall) : List Verdict :=
  (run p (fun _ _ => true) {} cs).map (·.decision.verdict)

/-! Undeclared, the mailbox names no resource, so reading it counts as the
highest label and the next push to a public repository is denied as a leak. -/
#guard verdicts undeclared [readMail, pushPublic] == [.allow, .deny]

/-! With `mail` declared public, both calls go through. -/
#guard verdicts declared [readMail, pushPublic] == [.allow, .allow]

/-! `UnlistedServerNamesNothing`: nothing is assumed about an undeclared
connection, not even that it names resources the way a code host does. -/
#guard knownLabel undeclared pushPublic == none

/-! `FlatServerLabel`: a flat server has its label whatever the arguments say. -/
#guard readLabel declared readMail == 0
#guard writeLabel declared readMail == 0

/-! `UnknownResourceIsSafe`: an undeclared server still reads at the top label
and writes at the bottom, so it can never be used to launder data. -/
#guard readLabel undeclared readMail == undeclared.top
#guard writeLabel undeclared readMail == 0

/-! Resource names are matched lowercased, as `owner/repo` is today. -/
#guard knownLabel declared pushPublic == some 0

/-! ## Capabilities

The frontier-risk template's oversight rule, written against a capability
instead of a tool-name shape, and pasted at the top as the template says. -/

def askSends : Rule :=
  { tool := "**", cap := some .sendMessage, conds := [], action := .ask,
    effect := .write, untrusted := true, highImpact := true }

def withOversight : Policy := { declared with rules := askSends :: demoRules }

def comment : ToolCall :=
  ⟨"github", "add_issue_comment", [("owner", .str "acme"), ("repo", .str "demo-public")]⟩
def push : ToolCall :=
  ⟨"github", "push_files", [("owner", .str "acme"), ("repo", .str "demo-public")]⟩

/-! It reaches the tool GitHub declared as sending messages … -/
#guard verdicts withOversight [comment] == [.ask]

/-! … and not the one it didn't, even though both are on the same server. -/
#guard verdicts withOversight [push] == [.allow]

/-! A server the policy doesn't list has no capabilities, so the rule can't
reach it. With no rule by name either, the call is denied, not asked. -/
def strayCall : ToolCall := ⟨"scanner", "send_report", []⟩
#guard capsOf withOversight strayCall == []
#guard verdicts withOversight [strayCall] == [.deny]

/-! `NameRulesUnchanged`: a rule with no capability is selected by name alone. -/
#guard (demoRules.all fun r => r.cap.isNone) == true

end GuardTest.Servers
