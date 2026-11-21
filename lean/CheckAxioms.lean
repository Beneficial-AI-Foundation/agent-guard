import Lean

/-!
# check-axioms

Loads the `Guard` library and checks every declaration in a `Guard.*` module.
Fails if any of them depends on an axiom outside Lean's standard three
(`propext`, `Classical.choice`, `Quot.sound`). That catches `sorry` (`sorryAx`),
`native_decide` (`Lean.ofReduceBool`) and any `axiom` declared in Guard.
-/

open Lean

def standardAxioms : List Name := [``propext, ``Classical.choice, ``Quot.sound]

def isGuardModule (m : Name) : Bool :=
  m == `Guard || (`Guard).isPrefixOf m

def main : IO UInt32 := do
  initSearchPath (← findSysroot)
  let env ← importModules #[{ module := `Guard }] {} (trustLevel := 1024)
  let mut checked := 0
  let mut failures : Array (Name × Array Name) := #[]
  for (name, _) in env.constants.map₁.toList do
    let some idx := env.getModuleIdxFor? name | continue
    let some mod := env.header.moduleNames[idx.toNat]? | continue
    unless isGuardModule mod do continue
    if name.isInternal then continue
    let (axs, _) ← (collectAxioms name : CoreM (Array Name)).toIO
      { fileName := "<check-axioms>", fileMap := default } { env }
    checked := checked + 1
    let bad := axs.filter (fun a => !standardAxioms.contains a)
    unless bad.isEmpty do
      failures := failures.push (name, bad)
  if checked == 0 then
    IO.eprintln "check-axioms: no Guard declarations found (is the library built?)"
    return 1
  for (name, bad) in failures do
    IO.eprintln s!"✗ {name} depends on {bad.toList}"
  if failures.isEmpty then
    IO.println s!"✓ {checked} Guard declarations checked: no sorry, standard axioms only"
    return 0
  else
    IO.eprintln s!"check-axioms: {failures.size} of {checked} declarations use non-standard axioms"
    return 1
