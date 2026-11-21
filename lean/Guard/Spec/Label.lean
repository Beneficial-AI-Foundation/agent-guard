/-!
# Labels

Confidentiality levels. A rule file lists label names from lowest to highest,
for example `labels: [public, private]`; the wire layer turns each name into its
position in that list. So `0` is the lowest level and higher numbers are more
secret, and "may data at level `a` flow to a place at level `b`" is `a ≤ b`.
-/

namespace Guard

/-- A confidentiality level: `0` is the lowest (e.g. `public`). -/
abbrev Label := Nat

end Guard
