# GitHub example

The GitHub profile lives in [`src/templates/github/`](../../src/templates/github/) so that `agentguard init github` and `agentguard demo` work from an installed package:

- `mcp.json`: GitHub's MCP server, as in VS Code.
- `rules.yaml`: the default rules (the everyday developer loop; merge, approve and push to main denied).
- `demo/mock_server.py`: an offline stand-in with the same tool names, and `demo-public` / `demo-private` repositories.
- `demo/stories/`: the six stories.

```bash
agentguard demo          # all six
agentguard demo 05       # just the poisoned issue
```

`tests/test_stories.py` runs the same stories in CI.

| # | Story | Theorem |
|---|---|---|
| 01 | Normal day: branch, push, PR, comment all allowed | — |
| 02 | Eager merge: denied; the agent asks a maintainer | `deny_rule_always_denies` |
| 03 | Push to main (or no branch): denied; it uses a branch | `deny_rule_always_denies` |
| 04 | Self-approval: `APPROVE` and `approve` denied; comment review allowed | `deny_rule_always_denies` |
| 05 | Poisoned issue: after reading it, pushes need a person; the workflow change is rejected | `no_untrusted_steering` |
| 06 | Leak: after reading `demo-private`, writing it to `demo-public` is denied | `no_exfiltration` |
