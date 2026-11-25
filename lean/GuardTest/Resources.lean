import Guard

/-!
The `resources` slot, on the two-connection profile that motivates it: a GitHub
server whose resource is `owner/repo`, and a mail server with no per-call
resource at all.
-/

namespace GuardTest.Resources
open Guard

def rd (tool : String) : Rule :=
  { tool, conds := [], action := .allow, effect := .read,
    untrusted := false, highImpact := false }

def wr (tool : String) : Rule :=
  { tool, conds := [], action := .allow, effect := .write,
    untrusted := false, highImpact := false }

def demoRepos : List RepoLabel := [⟨"*/demo-public", 0⟩, ⟨"*/demo-private", 1⟩]

def demoRules : List Rule :=
  [rd "github.get_file_contents", wr "github.push_files", rd "mail.read_inbox"]

/-- A rule file as they are written today: no `resources`. -/
def today : Policy := { labelCount := 2, repos := demoRepos, rules := demoRules }

/-- The same profile, with each server saying how it names a resource. -/
def declared : Policy :=
  { labelCount := 2, repos := demoRepos, rules := demoRules,
    resources := [⟨"github", .keys ["owner", "repo"]⟩, ⟨"mail", .flat 0⟩] }

def readMail : ToolCall := ⟨"mail", "read_inbox", [("folder", .str "INBOX")]⟩

def pushPublic : ToolCall :=
  ⟨"github", "push_files", [("owner", .str "Acme"), ("repo", .str "demo-public")]⟩

def verdicts (p : Policy) (cs : List ToolCall) : List Verdict :=
  (run p (fun _ _ => true) {} cs).map (·.decision.verdict)

/-! Today the mailbox is an unnameable resource, so reading it counts as the
highest label and the next push to a public repo is denied as a leak. -/
#guard verdicts today [readMail, pushPublic] == [.allow, .deny]

/-! With `mail` declared public, both calls go through. -/
#guard verdicts declared [readMail, pushPublic] == [.allow, .allow]

/-! `ResourceDefaultIsRepo` on this policy: no `resources` is the old behaviour. -/
#guard knownLabel today pushPublic == (repoOf pushPublic.args).bind (repoLabel today)

/-! `FlatServerLabel`: a flat server has its label whatever the arguments say. -/
#guard readLabel declared readMail == 0
#guard writeLabel declared readMail == 0

/-! `UnknownResourceIsSafe`: an undeclared server still reads at the top label. -/
#guard readLabel today readMail == today.top
#guard writeLabel today readMail == 0

/-! Resource names are matched lowercased, as `owner/repo` is today. -/
#guard knownLabel declared pushPublic == some 0

end GuardTest.Resources
