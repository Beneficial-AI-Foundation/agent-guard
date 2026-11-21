/-!
# Glob patterns (spec)

Patterns are used for tool names (`github.get_*`), argument values
(`.github/**`, `main`) and repository names (`*/demo-private`).

| Pattern | Matches                                            |
|---------|----------------------------------------------------|
| `**`    | any sequence of characters, including `/`          |
| `*`     | any sequence of characters except `/`              |
| `?`     | exactly one character except `/`                   |
| other   | itself, exactly (case-sensitive)                   |

There are no escapes and no character classes. `***` reads as `**` then `*`.

`Matches toks s` is the meaning of a pattern, written as inference rules. The
matcher that runs (`Guard.Impl.glob`) is a different algorithm, proved to agree
with this definition in `Guard.Proofs.Glob`.
-/

namespace Guard

/-- One token of a glob pattern. -/
inductive Tok where
  | lit (c : Char)
  | one
  | star
  | dstar
  deriving DecidableEq, Repr

/-- Splits a pattern into tokens, reading `**` before `*`. -/
def tokenize : List Char → List Tok
  | '*' :: '*' :: cs => .dstar :: tokenize cs
  | '*' :: cs => .star :: tokenize cs
  | '?' :: cs => .one :: tokenize cs
  | c :: cs => .lit c :: tokenize cs
  | [] => []

/-- `Matches p s`: the token list `p` matches the whole character list `s`. -/
inductive Matches : List Tok → List Char → Prop where
  | nil : Matches [] []
  | lit {c p s} : Matches p s → Matches (.lit c :: p) (c :: s)
  | one {d p s} : d ≠ '/' → Matches p s → Matches (.one :: p) (d :: s)
  /-- `*` matches nothing … -/
  | starNone {p s} : Matches p s → Matches (.star :: p) s
  /-- … or one more character that isn't `/`. -/
  | starMore {d p s} : d ≠ '/' → Matches (.star :: p) s → Matches (.star :: p) (d :: s)
  /-- `**` matches nothing … -/
  | dstarNone {p s} : Matches p s → Matches (.dstar :: p) s
  /-- … or one more character, `/` included. -/
  | dstarMore {d p s} : Matches (.dstar :: p) s → Matches (.dstar :: p) (d :: s)

/-- The pattern string `pat` matches the whole string `s`. -/
def Glob (pat s : String) : Prop :=
  Matches (tokenize pat.toList) s.toList

end Guard
