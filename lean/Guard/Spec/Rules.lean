import Guard.Spec.Label

/-!
# Tool calls, rules and policies

A **tool call** is what the agent asks an MCP server to do: a server name, a
tool name and JSON arguments. A **policy** is a rule file after validation: an
ordered list of rules, the number of labels, and which label each resource has.

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

/-- Whether a call reads data from the resource it touches, writes to it, or both. -/
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

/-- **What a tool does.** A closed vocabulary: a connection's template says
which of its tools have each capability, and a rule can select on the
capability instead of guessing tool names. The list is deliberately short, and
the wire layer rejects any name outside it, so a typo is an error rather than a
rule that silently never fires.

The twelve come from the agent-action rules of the FLI AI Safety Index and
AIR-Bench 2024 (see `docs/frontier-risk.md`). -/
inductive Capability where
  | networkScan            -- port and vulnerability scanning
  | remoteAccess           -- logging in to a machine
  | packetForge            -- raw packets, spoofed traffic
  | malwareExec            -- running unsandboxed code
  | serviceDisrupt         -- flooding, network reconfiguration
  | auditTamper            -- editing logs or records of what happened
  | guardConfigWrite       -- writing AgentGuard's own configuration
  | sendMessage            -- anything an outsider receives
  | automatedDecision      -- a decision about a person (qualify with `when`)
  | operatePhysicalSystem  -- machinery, vehicles, grids, weapons, life support
  | readData
  | writeData
  deriving DecidableEq, Repr

structure Rule where
  /-- Pattern for the tool name, e.g. `github.push_files` or `github.get_*`.
  A rule that selects on `cap` alone leaves this `**`. -/
  tool : String
  /-- If set, the rule applies only to calls whose server declared this
  capability for the tool. `none` means the rule is selected by name alone, as
  every rule is today. -/
  cap : Option Capability := none
  /-- All conditions must hold for the rule to apply. -/
  conds : List Cond
  action : Action
  effect : Effect
  /-- The result contains text from outsiders (issues, comments, PRs). -/
  untrusted : Bool
  /-- The call changes something that matters (push, PR, workflow). -/
  highImpact : Bool
  deriving Repr

/-- `match: "*/demo-private", label: private`: a resource name pattern and the
label of everything it names. -/
structure ResourceLabel where
  pat : String
  label : Label
  deriving Repr

/-- **How a server names the thing a call touches.** The label system needs a
name for the data a call reads or writes. GitHub calls it `owner/repo`; another
server may name it differently, or not at all.

* `keys names` — join the call's top-level arguments `names`, in order, with
  `/`. The result is matched against the policy's `resources` patterns. If any
  key is missing the resource is unknown.
* `flat l` — every call on this server touches data at label `l`. For servers
  with no per-call resource (a mailbox, a scanner), where treating each call as
  unknown would push the session to the top label on its first read. -/
inductive Resource where
  | keys (names : List String)
  | flat (label : Label)
  deriving Repr

/-- `send_message: [add_issue_comment, "send_*"]`: the tools of one server that
have this capability. Patterns match the **tool** name, not `server.tool`. -/
structure CapTools where
  cap : Capability
  tools : List String
  deriving Repr

/-- One connection: how it names resources, and what its tools do. -/
structure Server where
  /-- Pattern for the server's name in the profile, e.g. `github` or `mail-*`. -/
  name : String
  resource : Option Resource := none
  caps : List CapTools := []
  deriving Repr

structure Policy where
  /-- Number of labels; the highest label is `labelCount - 1`. -/
  labelCount : Nat
  /-- Resource names and their labels. First match wins. -/
  resources : List ResourceLabel
  /-- First match wins; no match means deny. -/
  rules : List Rule
  /-- The connections: how each names the resource a call touches, and which of
  its tools have each capability. First match wins. A server that is not listed
  names no resource and has no capabilities. -/
  servers : List Server := []
  deriving Repr

/-- The highest label. -/
def Policy.top (p : Policy) : Label :=
  p.labelCount - 1

end Guard
