#!/usr/bin/env bash
# Build the Lean core with warnings as errors, then check axioms.
# Fails on any `sorry`, `native_decide`, or non-standard axiom in Guard.*.
set -euo pipefail
cd "$(dirname "$0")/../lean"

lake build --wfail
lake build GuardTest --wfail
lake exe check-axioms
lake exe guard-worker --info
