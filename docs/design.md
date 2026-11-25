# Design decisions

Why AgentGuard is built the way it is. What the pieces are: [architecture.md](architecture.md). What rules mean: [rules.md](rules.md). What is proved: [proofs.md](proofs.md).

## Scope

- **One real connection: the official GitHub MCP server.** It's widely used, it connects the same way as in VS Code, and outsiders can write issues and comments, so prompt injection arrives naturally. More connections come later as new template folders, not new gateway code.
- **Connecting feels like VS Code.** A profile's `mcp.json` accepts what VS Code, Claude Code or Cursor accept: local commands, remote URLs with headers, `${env:VAR}` from `.env`, and either the `servers` or the `mcpServers` key.

## The whole decision is in Lean

- Lean parses the rules and the raw tool call, matches tool, capability, argument and resource patterns, classifies the call, decides, and updates the session. Python converts YAML to JSON, moves bytes, and forwards only on allow.
- **`Spec/` is the meaning, `Proofs/` proves it.** The spec is executable, so the worker runs `Guard.step` from `Spec/` itself. Only glob matching has a separate, faster implementation (`Impl/Glob.lean`), proved equal to the spec. Less separate code means less to trust.
- Theorem statements are written first and reviewed by a person before they are proved. They are stated over whole runs, for every rule file, call sequence and approver.
- Lean 4 without Mathlib: glob matching and argument lookup are written and proved by hand.

## Rule semantics

- **First matching rule decides; no match means deny.**
- **Conditions fail safe.** For `deny` and `ask` rules a condition holds if the argument is missing or any value matches; for `allow` rules only if it's present and every value matches. A condition sees every value of its key at any depth (`files[].path` too).
- **Omitted attributes take the safe value:** `effect: readwrite`, `source: untrusted`, `impact: high`. Unknown keys are errors.
- **Resource names are lowercased** before matching, because many services are case-insensitive (`Demo-Private` must not escape `*/demo-private`). A resource the policy can't name counts as the highest label when read and the lowest when written, so a template lists its resources rather than using a `*` catch-all.
- **`**.github/**`, not `.github/workflows/**`,** in the ask rule: it also catches `./.github/…`, `CODEOWNERS` and actions.
- **Reviews use an allowlist** (`COMMENT`, `REQUEST_CHANGES`); anything else, including `approve`, is denied.

## Sessions

- **The Lean worker is stateless about sessions.** Each request carries the session and the reply carries the next one, so restarting the worker loses nothing.
- **Sessions are keyed on the agent's identity**, not on an MCP session id (the 2026-07-28 HTTP protocol has none): one per `agentguard stdio` process, one per gateway token over HTTP. Reconnecting doesn't reset a session; a person ends it in the console.
- **One decision at a time per session**, held while the call is forwarded, so parallel calls can't race the session state.

## Credentials

- **A fine-grained token in the profile's `.env`**, limited to the repositories the agent may touch, sent as the `Authorization` header exactly as VS Code's `mcp.json` would. The agent never sees it, and it is never logged.
- **No sign-in flow of its own.** An earlier version had GitHub App device-flow and OAuth sign-in with a keychain token store; the real-GitHub test showed a token is all that's needed, so that code was removed.
- **Agents connecting to AgentGuard** over HTTP need no token by default (the gateway listens on 127.0.0.1). Setting `AGENTGUARD_GATEWAY_TOKEN` makes the gateway require it as a bearer token.

## The console

It answers only loopback `Host` headers (which blocks other sites and DNS rebinding), and each run has a token in the URL fragment that the page sends as a header.

## Protocol compatibility

AgentGuard serves agents on MCP 2025-11-25 as well as 2026-07-28. The older version requires a tool's output schema to be an object schema and structured content to be an object. GitHub's server sends other schemas (`"type": ["object", "null"]`, a root `oneOf`), so the gateway drops those optional schemas and any structured content that isn't an object. The result's content still reaches the agent.

## Testing

Real GitHub is the end-to-end test: the six stories run against a throwaway organisation, scripted (`make live`) and then with a real agent ([testing.md](testing.md)). There is no mock GitHub server. The gateway's own tests use a tiny echo server, and the property test compares Lean with an independent Python copy on 10,000 random cases.

## Performance

About 78 µs per decision including JSON (10,000 calls with 33 rules and 5 files each in 0.78 s). A pathological pattern on a 20,000-character value takes 60 ms in total.

## Open questions

- A `deny` condition also holds when its argument is missing, so a rule can't deny a call only when an optional flag (such as `allow_symlink_write`) is set.
- `pull_request_review_write` with `method: resolve_thread` is denied by the review allowlist, because it has no `event`.
