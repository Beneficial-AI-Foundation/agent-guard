# Threat model

## What AgentGuard defends against

An AI agent that has been tricked or is simply wrong: prompt injection in an issue, comment or pull request; an agent too eager to merge, approve or push to main; an agent that copies private data somewhere public. The agent may choose any sequence of tool calls with any arguments. The [theorems](proofs.md) hold for all of them.

## What is proved

The whole decision: matching rules to a call (tool names, argument values, repository names), classifying the call, the verdict, and how the session state changes. See [proofs.md](proofs.md).

## What is trusted rather than proved

| Component | What we rely on | How the risk is reduced |
|---|---|---|
| Lean kernel and compiler | Proofs are checked correctly, and compiled code behaves like the definitions | Widely used; `check-axioms` rejects `native_decide` and extra axioms |
| JSON layer (`lean/Guard/Wire/`) | Turns JSON into the spec's types faithfully | Small, tested; errors mean deny; unknown keys rejected |
| Lean's JSON parser | Parses requests correctly; duplicate keys resolve last-wins | Python's `json` also resolves last-wins, and the gateway sends Lean exactly the arguments it forwards |
| YAML → JSON (`src/profile/rules.py`) | Mechanical conversion | Lean validates the result |
| Forwarding code (`src/proxy/guard.py`) | Forwards a call only on allow, or on ask after approval | About 20 lines, reviewed and tested |
| Session bookkeeping in the gateway | Stores the `next` session Lean returns and sends it back unchanged | Lean rejects out-of-range sessions; tests |
| MCP SDK, GitHub, the GitHub MCP server | Do what the tool call says | Out of scope |
| The rule file and labels | Describe reality: which repositories are private, which tools return outsider text, which calls are high impact | Safe defaults for omitted attributes; unknown repositories count as private when read and public when written; `agentguard try` shows what a rule file does |

## Known limits

- **Only what passes through.** AgentGuard only sees calls sent through it. `agentguard doctor` looks for bypasses (a direct GitHub server in the agent's config, a signed-in `gh` CLI), but an agent with a shell and a token can go around any gateway.
- **What a session is.** MCP's 2026-07-28 protocol is stateless over HTTP (no session id), so the transport can't say which calls belong together. AgentGuard defines a session by the agent's identity: one per `agentguard stdio` process, and one per gateway token over HTTP, until AgentGuard restarts or a person ends it in the console. Reconnecting doesn't start a new session. Merging calls into one session only raises the level, so this errs on the safe side. Give each agent its own token if they should have separate sessions.
- **Session-level memory.** The session level and the untrusted mark cover everything the agent read in that session. AgentGuard can't tell which output came from which input, so a session that read private data can't write to public repositories until it ends.
- **Labels are about repositories.** Data inside a public repository is treated as public, data from a private one as private. GitHub itself (search, notifications) is trusted not to leak between them.
- **Branch names are compared exactly.** If a repository's default branch isn't called `main` or `master`, add it to the deny rule.
- **Tool names and arguments** in the GitHub template are from the official GitHub MCP server and need checking against each server version (`agentguard try` lists the live tools).
- **The audit log redacts, it doesn't encrypt.** Secret-named arguments, known token formats, `NAME=value` assignments with secret-like names, and long text are fingerprinted; every argument of a call denied as a leak is fingerprinted. Other free text is logged as written. The file is created readable only by its owner.
- **Research prototype.** Not yet reviewed or used in production.
