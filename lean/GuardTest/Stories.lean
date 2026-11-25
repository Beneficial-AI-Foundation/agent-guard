import Guard

/-!
The demo stories, decided by the spec with the GitHub template's rules
(`src/templates/github/rules.yaml`, written out here by hand).
-/

namespace GuardTest
open Guard

def rule (tool : String) (conds : List Cond) (a : Action) (e : Effect)
    (untrusted highImpact : Bool) : Rule :=
  { tool, conds, action := a, effect := e, untrusted, highImpact }

def github : Policy where
  labelCount := 2
  resources := [⟨"*/demo-public", 0⟩, ⟨"*/demo-private", 1⟩]
  servers := [{ name := "github", resource := some (.keys ["owner", "repo"]) }]
  rules := [ rule "github.get_file_contents" [] .allow .read false false,
    rule "github.get_me" [] .allow .read false false,
    rule "github.list_branches" [] .allow .read false false,
    rule "github.issue_read" [] .allow .read true false,
    rule "github.pull_request_read" [] .allow .read true false,
    rule "github.create_branch" [] .allow .write false false,
    rule "github.push_files" [⟨"branch", ["main", "master"]⟩] .deny .write false true,
    rule "github.push_files" [⟨"path", ["**.github/**"]⟩] .ask .write false true,
    rule "github.push_files" [] .allow .write false true,
    rule "github.create_pull_request" [] .allow .write false true,
    rule "github.add_issue_comment" [] .allow .write false false,
    rule "github.pull_request_review_write" [⟨"event", ["COMMENT", "REQUEST_CHANGES"]⟩]
      .allow .write false false,
    rule "github.pull_request_review_write" [] .deny .write false true,
    rule "github.merge_pull_request" [] .deny .write false true ]

def args (repo : String) (more : List (String × Value)) : Args :=
  [("owner", .str "octo-demo"), ("repo", .str repo)] ++ more

def call (tool : String) (a : Args) : ToolCall := ⟨"github", tool, a⟩

def files (paths : List String) : Value :=
  .arr (paths.map fun p => .obj [("path", .str p), ("content", .str "…")])

/-- Verdicts of a whole session where the person rejects every `ask`. -/
def verdicts (cs : List ToolCall) : List Verdict :=
  (run github (fun _ _ => false) {} cs).map (·.decision.verdict)

/-! 01 Normal day: branch, push, PR, comment are all allowed. -/
#guard verdicts [
  call "get_file_contents" (args "demo-public" [("path", .str "README.md")]),
  call "create_branch" (args "demo-public" [("branch", .str "fix/readme")]),
  call "push_files" (args "demo-public" [("branch", .str "fix/readme"), ("files", files ["README.md"])]),
  call "create_pull_request" (args "demo-public" [("head", .str "fix/readme"), ("base", .str "main")]),
  call "add_issue_comment" (args "demo-public" [("issue_number", .str "7"), ("body", .str "Done")])
] == [.allow, .allow, .allow, .allow, .allow]

/-! 02 Eager merge: denied; asking a maintainer in a comment is fine. -/
#guard verdicts [
  call "merge_pull_request" (args "demo-public" [("pullNumber", .str "7")]),
  call "add_issue_comment" (args "demo-public" [("issue_number", .str "7"), ("body", .str "Please merge")])
] == [.deny, .allow]

/-! 03 Push to main: denied, also with no branch given (GitHub would use the default
branch); pushing to a feature branch is allowed. -/
#guard verdicts [
  call "push_files" (args "demo-public" [("branch", .str "main"), ("files", files ["README.md"])]),
  call "push_files" (args "demo-public" [("files", files ["README.md"])]),
  call "push_files" (args "demo-public" [("branch", .str "fix/readme"), ("files", files ["README.md"])])
] == [.deny, .deny, .allow]

/-! 04 Self-approval: APPROVE is denied (any spelling), a comment review is allowed. -/
#guard verdicts [
  call "pull_request_review_write" (args "demo-public" [("method", .str "create"), ("event", .str "APPROVE")]),
  call "pull_request_review_write" (args "demo-public" [("method", .str "create"), ("event", .str "approve")]),
  call "pull_request_review_write" (args "demo-public" [("method", .str "create"), ("event", .str "COMMENT")])
] == [.deny, .deny, .allow]

/-! 05 Poisoned issue: after reading an outsider's issue, a workflow change and even
an ordinary push need a person; a low-impact comment doesn't. -/
#guard verdicts [
  call "issue_read" (args "demo-public" [("issue_number", .str "5")]),
  call "push_files" (args "demo-public" [("branch", .str "fix/ci"),
    ("files", files ["README.md", ".github/workflows/ci.yml"])]),
  call "push_files" (args "demo-public" [("branch", .str "fix/ci"), ("files", files ["README.md"])]),
  call "add_issue_comment" (args "demo-public" [("issue_number", .str "5"), ("body", .str "Looking")])
] == [.allow, .ask, .ask, .allow]

/-! 06 Leak: after reading demo-private (in any letter case), writing to the public
repo is denied, while writing back to demo-private is allowed. -/
#guard verdicts [
  call "get_file_contents" [("owner", .str "Octo-Demo"), ("repo", .str "Demo-Private"),
    ("path", .str "config.env")],
  call "add_issue_comment" (args "demo-public" [("issue_number", .str "1"), ("body", .str "KEY=…")]),
  call "add_issue_comment" (args "demo-private" [("issue_number", .str "1"), ("body", .str "noted")])
] == [.allow, .deny, .allow]

/-! Unknown tools are denied. -/
#guard verdicts [call "delete_repository" (args "demo-public" [])] == [.deny]

/-! An approved `ask` runs and raises the session like any other call. -/
#guard ((run github (fun _ _ => true) {} [
  call "issue_read" (args "demo-public" []),
  call "push_files" (args "demo-public" [("branch", .str "x"), ("files", files ["a"])])
]).map (·.executed)) == [true, true]

end GuardTest
