import Guard.Spec.Label

/-!
# Tool calls, rules and policies

A **tool call** is what the agent asks an MCP server to do: a server name, a
tool name and JSON arguments. A **policy** is a rule file after validation: an
ordered list of rules, the number of labels, and which label each repository has.

Every rule attribute that a rule file may leave out takes its **safe value**
when omitted (see `Guard.Wire.Validate`):

| Attribute     | Omitted means | Why it's the safe choice                                  |
|---------------|---------------|-----------------------------------------------------------|
| `effect`      | `readwrite`   | raises the session level *and* is checked as a write      |
| `untrusted`   | `true`        | after it, high-impact calls need a person                 |
| `highImpact`  | `true`        | needs a person after untrusted input                      |
-/

namespace Guard

/-- A JSON value, reduced to what rules can look at. Numbers and booleans become
their JSON text (`7`, `true`); `null` carries no value. -/
inductive Value where
  | str (s : String)
  | null
  | arr (xs : List Value)
  | obj (kvs : List (String × Value))
  deriving Repr, Inhabited

/-- Tool-call arguments: the top-level JSON object. -/
abbrev Args := List (String × Value)

structure ToolCall where
  /-- The server's name in the profile, e.g. `github`. -/
  server : String
  /-- The tool's name on that server, e.g. `push_files`. -/
  tool : String
  args : Args
  deriving Repr, Inhabited

/-- The name rules match against: `github.push_files`. -/
def ToolCall.name (c : ToolCall) : String :=
  c.server ++ "." ++ c.tool

/-- What a rule says, and also the verdict on a call. -/
inductive Action where
  | allow
  | ask
  | deny
  deriving DecidableEq, Repr, Inhabited

abbrev Verdict := Action

/-- Whether a call reads data from its repository, writes to it, or both. -/
inductive Effect where
  | read
  | write
  | readwrite
  deriving DecidableEq, Repr

def Effect.reads : Effect → Bool
  | .read | .readwrite => true
  | .write => false

def Effect.writes : Effect → Bool
  | .write | .readwrite => true
  | .read => false

/-- A condition on one argument: `branch: [main, master]`. -/
structure Cond where
  key : String
  /-- The value must match at least one of these patterns. -/
  pats : List String
  deriving Repr

structure Rule where
  /-- Pattern for the tool name, e.g. `github.push_files` or `github.get_*`. -/
  tool : String
  /-- All conditions must hold for the rule to apply. -/
  conds : List Cond
  action : Action
  effect : Effect
  /-- The result contains text from outsiders (issues, comments, PRs). -/
  untrusted : Bool
  /-- The call changes something that matters (push, PR, workflow). -/
  highImpact : Bool
  deriving Repr

/-- `match: "*/demo-private", label: private`. -/
structure RepoLabel where
  pat : String
  label : Label
  deriving Repr

structure Policy where
  /-- Number of labels; the highest label is `labelCount - 1`. -/
  labelCount : Nat
  /-- First match wins. -/
  repos : List RepoLabel
  /-- First match wins; no match means deny. -/
  rules : List Rule
  deriving Repr

/-- The highest label. -/
def Policy.top (p : Policy) : Label :=
  p.labelCount - 1

end Guard
