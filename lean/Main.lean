import Guard
import Guard.Wire.Validate

/-!
# guard-worker

Reads one JSON request per line on stdin and writes one JSON response per line.
It keeps only the loaded policy; the session state travels in each request and
comes back in `next`, so a restarted worker loses nothing.

Requests (an optional `"id"` is echoed back):

* `{"op":"load","policy":{…}}` → `{"ok":true,"rules":N,"labels":[…]}` or
  `{"ok":false,"errors":[…]}`. A rejected policy leaves the previous one in force.
* `{"op":"step","session":{"level":0,"tainted":false},"call":{"server":"github","tool":"push_files","arguments":{…}}}`
  → `{"ok":true,"verdict":"deny","cause":"rule","rule":4,"theorem":"…","next":{…},"class":{…}}`
* `{"op":"info"}` → version and theorem list.

Any error → `{"ok":false,"error":"…"}`; the gateway treats that as deny.
-/

open Lean Guard Guard.Wire

def info : Json :=
  Json.mkObj [
    ("name", "guard-worker"),
    ("version", Json.str Guard.version),
    ("theorems", Json.arr (Guard.theorems.map Json.str).toArray)
  ]

def reply (id : Json) (ok : Bool) (fields : List (String × Json)) : Json :=
  Json.mkObj ((if id.isNull then [] else [("id", id)]) ++ ("ok", toJson ok) :: fields)

def handle (policy : IO.Ref (Option Policy)) (line : String) : IO Json := do
  match Json.parse line with
  | .error e => return reply .null false [("error", Json.str s!"invalid JSON: {e}")]
  | .ok req =>
    let id := req.getObjValD "id"
    let fail (msg : String) := reply id false [("error", Json.str msg)]
    match req.getObjVal? "op" with
    | .ok (.str "info") => return reply id true [("info", info)]
    | .ok (.str "load") =>
      match req.getObjVal? "policy" with
      | .error _ => return fail "load: policy is missing"
      | .ok pj =>
        match decodePolicy pj with
        | .error errs => return reply id false [("errors", toJson errs)]
        | .ok p =>
          policy.set (some p)
          return reply id true [("rules", toJson p.rules.length),
            ("labels", toJson p.labelCount)]
    | .ok (.str "step") =>
      let some p ← policy.get | return fail "step: no policy loaded"
      let r : Except String Decision := do
        let s ← decodeSession p (req.getObjValD "session")
        let c ← decodeCall (← req.getObjVal? "call" |>.mapError (fun _ => "step: call is missing"))
        pure (step p s c)
      match r with
      | .error e => return fail e
      | .ok d => return reply id true (encodeDecision d)
    | .ok (.str op) => return fail s!"unknown op \"{op}\""
    | _ => return fail "op is missing"

partial def loop (policy : IO.Ref (Option Policy)) (stdin : IO.FS.Stream) (stdout : IO.FS.Stream) :
    IO Unit := do
  let line ← stdin.getLine
  if line.isEmpty then return  -- end of input
  let line := line.trimAsciiEnd.toString
  unless line.isEmpty do
    let out ← handle policy line
    stdout.putStrLn out.compress
    stdout.flush
  loop policy stdin stdout

def main (args : List String) : IO UInt32 := do
  match args with
  | ["--info"] =>
    IO.println info.compress
    return 0
  | ["--version"] =>
    IO.println s!"guard-worker {Guard.version}"
    return 0
  | [] =>
    let policy ← IO.mkRef none
    loop policy (← IO.getStdin) (← IO.getStdout)
    return 0
  | _ =>
    IO.eprintln "usage: guard-worker [--info | --version]   (no argument: JSON lines on stdin)"
    return 2
