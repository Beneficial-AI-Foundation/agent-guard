import Guard.Spec.Semantics

/-!
# Sessions and the decision

A **session** remembers two things about what the agent has already seen:

* `level`: the highest label of anything it has read (starts at `0`);
* `tainted`: whether it has read text written by outsiders.

Neither ever goes back down: rewording data doesn't launder it.

## Resources

Every call touches a **resource**, and the resource's label is what the leak
rules are about. A policy's `servers` says how each one names a resource:

* `keys [owner, repo]` — join those top-level arguments with `/`. The result is
  matched against the `resources` patterns, first match wins.
* `flat l` — every call on that server touches data at label `l`.

Names and patterns are compared **lowercased**, because many services treat
names case-insensitively: `Demo-Private` must not escape a `*/demo-private`
pattern.

A server the policy does not list, or that says nothing about resources, names
no resource at all.

If the call names no resource, or no `resources` entry matches, the label is
unknown and counts in the safe direction: **reading** it counts as the highest
label, **writing** to it counts as the lowest. That is safe but costly for a
server with no per-call resource: its first read pushes the session to the top
label, and writes below that are then denied as leaks. `flat` is the way to say
what such a server holds.

## The decision (`step`), in order

1. The rules say deny (or no rule applies)             → **deny**
2. It writes somewhere below the session level         → **deny** (leak)
3. The rules say ask                                   → **ask**
4. The session is tainted and the call is high impact  → **ask**
5. Otherwise                                           → **allow**

A call that runs (allowed, or asked and approved) then raises the session:
`level := max level readLevel`, `tainted := tainted || untrusted`.
-/

namespace Guard

structure Session where
  level : Label := 0
  tainted : Bool := false
  deriving DecidableEq, Repr, Inhabited

/-! ## Repository labels -/

def lower (s : String) : String :=
  s.map Char.toLower

/-- The top-level string argument `k`, if there is one. -/
def lookupStr (args : Args) (k : String) : Option String :=
  match args.find? (·.1 == k) with
  | some (_, .str s) => some s
  | _ => none

/-- The values of `names`, in order, joined with `/` and lowercased. Every key
must be present, or the resource has no name. -/
def resourceName (names : List String) (args : Args) : Option String :=
  match names with
  | [] => none
  | _ => (names.mapM (lookupStr args)).map fun vs => lower (String.intercalate "/" vs)

/-- How the call's server names a resource, if the policy lists it and it says. -/
def serverResource (p : Policy) (c : ToolCall) : Option Resource :=
  (serverOf p c).bind (·.resource)

/-- The label of the first `resources` entry matching the resource name. -/
def resourceLabel (p : Policy) (name : String) : Option Label :=
  (p.resources.find? (fun r => decide (Glob (lower r.pat) name))).map (·.label)

def knownLabel (p : Policy) (c : ToolCall) : Option Label :=
  match serverResource p c with
  | some (.flat l) => some l
  | some (.keys names) => (resourceName names c.args).bind (resourceLabel p)
  | none => none

/-- Reading an unknown repository counts as the highest label. -/
def readLabel (p : Policy) (c : ToolCall) : Label :=
  (knownLabel p c).getD p.top

/-- Writing to an unknown repository counts as the lowest label. -/
def writeLabel (p : Policy) (c : ToolCall) : Label :=
  (knownLabel p c).getD 0

/-! ## Classifying a call -/

/-- Everything the decision needs to know about one call. -/
structure Class where
  /-- The first rule that applies (0-based position), if any. -/
  rule : Option (Nat × Rule)
  action : Action
  /-- Label of what the call reads (`0` if it reads nothing). -/
  readLevel : Label
  /-- Labels of the places it writes to. -/
  dests : List Label
  untrusted : Bool
  highImpact : Bool
  deriving Repr

def classify (p : Policy) (c : ToolCall) : Class :=
  match firstMatch p p.rules c with
  | some (i, r) =>
    { rule := some (i, r)
      action := r.action
      readLevel := if r.effect.reads then readLabel p c else 0
      dests := if r.effect.writes then [writeLabel p c] else []
      untrusted := r.untrusted
      highImpact := r.highImpact }
  | none =>
    -- Denied anyway; the other fields take their safe values.
    { rule := none, action := .deny, readLevel := p.top, dests := [0]
      untrusted := true, highImpact := true }

/-- The session after a call has run. -/
def Session.absorb (s : Session) (k : Class) : Session :=
  { level := max s.level k.readLevel, tainted := s.tainted || k.untrusted }

/-! ## The decision -/

/-- Why the verdict was reached (for the audit log and the agent's error message). -/
inductive Cause where
  | rule       -- the first applying rule said deny or ask
  | noRule     -- no rule applies
  | leak       -- it would write below the session level
  | untrusted  -- high impact after outsider text
  | allowed
  deriving DecidableEq, Repr

structure Decision where
  verdict : Verdict
  cause : Cause
  cls : Class
  /-- The session if the call runs. -/
  next : Session
  deriving Repr

def step (p : Policy) (s : Session) (c : ToolCall) : Decision :=
  let k := classify p c
  if k.action = .deny then
    { verdict := .deny, cause := if k.rule.isSome then .rule else .noRule, cls := k, next := s }
  else if k.dests.any (· < s.level) then
    { verdict := .deny, cause := .leak, cls := k, next := s }
  else if k.action = .ask then
    { verdict := .ask, cause := .rule, cls := k, next := s.absorb k }
  else if s.tainted && k.highImpact then
    { verdict := .ask, cause := .untrusted, cls := k, next := s.absorb k }
  else
    { verdict := .allow, cause := .allowed, cls := k, next := s.absorb k }

/-! ## A whole session -/

/-- Does a call with this verdict run? `ask` runs only if the person approves. -/
def runs (v : Verdict) (approved : Bool) : Bool :=
  match v with
  | .allow => true
  | .ask => approved
  | .deny => false

/-- One decided call in a session. -/
structure Event where
  call : ToolCall
  before : Session
  decision : Decision
  executed : Bool
  after : Session

/-- Decides a sequence of calls. `approve` is the person answering `ask`
verdicts: it can be anyone, and the theorems hold whatever it answers. -/
def run (p : Policy) (approve : Session → ToolCall → Bool) :
    Session → List ToolCall → List Event
  | _, [] => []
  | s, c :: cs =>
    let d := step p s c
    let ex := runs d.verdict (approve s c)
    let s' := if ex then d.next else s
    { call := c, before := s, decision := d, executed := ex, after := s' } :: run p approve s' cs

end Guard
