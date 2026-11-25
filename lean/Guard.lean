import Guard.Spec.Glob
import Guard.Impl.Glob
import Guard.Proofs.Glob
import Guard.Spec.Safety
import Guard.Proofs.Safety
import Guard.Wire.Validate

/-!
# Guard

The proved decision behind AgentGuard.

* `Guard.Spec`   – short, readable definitions of what rules mean (what reviewers read).
* `Guard.Impl`   – the glob matcher that runs (everything else runs the spec's own definitions).
* `Guard.Proofs` – the matcher agrees with the spec, and the safety theorems stated in
  `Guard.Spec.Safety` hold.
* `Guard.Wire`   – JSON decoding and rule-file validation.
-/

namespace Guard

/-- Version of the decision core, reported by `guard-worker --info`. -/
def version : String := "0.0.1"

/-- Names of the proved safety theorems, reported by `guard-worker --info`. -/
def theorems : List String :=
  [ "impl_eq_spec", "executed_only_if_allowed", "unmatched_denied",
    "deny_rule_always_denies", "ask_rule_needs_person", "allow_needs_allow_rule",
    "no_exfiltration", "level_monotone", "no_untrusted_steering", "approval_cannot_leak",
    "resource_default_is_repo", "flat_server_label", "unknown_resource_is_safe" ]

end Guard
