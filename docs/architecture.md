# Architecture

```
 agent (VS Code, Claude Code, Cursor)
   │  MCP (stdio or HTTP :8080/mcp)
   ▼
 AgentGuard gateway (src/)                    console :7070 (feed, approvals)
   │  1. call → JSON line ──────────────▶ guard-worker (lean/, Lean 4)
   │  2.        verdict + next session ◀──  Guard.step: proved decision
   │  3. allow → forward · ask → person · deny → "Blocked by AgentGuard: …"
   ▼  MCP (stdio or HTTP, signed in via device flow / OAuth)
 GitHub MCP server
```

## The pieces

| Piece | Where | Trusted or proved |
|---|---|---|
| Rule meaning, the decision, session update | `lean/Guard/Spec/` | Spec (read by reviewers) |
| Glob matcher | `lean/Guard/Impl/Glob.lean` | Proved equal to the spec |
| Safety theorems | `lean/Guard/Proofs/` | Proved |
| JSON in/out, rule-file validation | `lean/Guard/Wire/`, `lean/Main.lean` | Trusted, tested |
| Worker client (errors → deny, restart) | `src/monitor/worker.py` | Trusted, tested |
| Forwarding | `src/proxy/guard.py` | Trusted, ~20 lines of logic |
| Profiles, YAML → JSON | `src/profile/` | Trusted, mechanical |
| Sign-in | `src/auth/` | Trusted |

## A call, step by step

1. The agent calls `push_files`. The gateway finds which upstream server has it.
2. It takes the agent's session lock (one decision at a time per session) and sends Lean `{"op":"step","session":{"level":0,"tainted":true},"call":{…}}`.
3. Lean answers `{"verdict":"ask","cause":"untrusted","rule":19,"next":{…}}`.
4. `ask`: the console shows an approval card with the outsider text the session read. Approve → forward; reject or no answer in 5 minutes → blocked.
5. When a call runs, the session becomes Lean's `next`. The audit log gets one line.

## Sessions

The Lean worker is stateless about sessions: each request carries the session and the reply carries `next`, so a crashed worker restarts without losing anything. The gateway keys sessions on the agent's identity (one per `agentguard stdio` process, one per gateway token over HTTP), because MCP's 2026-07-28 HTTP protocol has no session id. See [threat-model.md](threat-model.md).

## Modes

- `enforce`: apply the verdict.
- `audit`: decide and log, but forward everything (to tune rules before enforcing).
- `off`: forward unchecked.
