# Writing rules

A rule file (`rules.yaml`) says what an agent may do through AgentGuard. Its meaning is defined in Lean, in [`lean/Guard/Spec/`](../lean/Guard/Spec/); this page explains the same thing in words.

```yaml
labels: [public, private]          # lowest first
servers:                           # the connections: what they name, what their tools do
  - name: github
    resource: { keys: [owner, repo] }
    capabilities: { write_data: [push_files] }
resources:                         # resource names and their labels; first match wins
  - { match: "*/demo-public",  label: public }
  - { match: "*/demo-private", label: private }
rules:                             # first match wins; no match means deny
  - { tool: github.get_file_contents, action: allow, effect: read, source: trusted, impact: low }
  - { tool: github.push_files, when: { branch: [main, master] }, action: deny, effect: write }
  - { tool: github.push_files, when: { path: "**.github/**" },   action: ask,  effect: write }
  - { tool: github.push_files, action: allow, effect: write, source: trusted, impact: high }
```

## How a call is decided

1. **Find the rule.** Rules are tried in order. A rule applies when its `tool` pattern matches the call's name (`github.push_files`: server name, a dot, tool name) and every condition under `when` holds. **The first rule that applies decides.** If none applies, the call is **denied**.
2. **Deny** if that rule says `deny`.
3. **Deny** if the call writes to a resource whose label is below the session level (a leak).
4. **Ask a person** if the rule says `ask`.
5. **Ask a person** if the session has read outsider text and the call is high impact.
6. Otherwise **allow**.

A call that runs (allowed, or approved by a person) then raises the session: its level becomes the highest label read so far, and reading outsider text marks it as untrusted for the rest of the session. Neither goes back down.

## Rule fields

| Field | Values | If omitted | Meaning |
|---|---|---|---|
| `tool` | pattern | required unless `capability` is given | Tool name, e.g. `github.push_files`, `github.get_*` |
| `capability` | one of the twelve below | no capability | Select on what the tool does. The rule reaches only tools a server declared for it |
| `when` | map of argument → pattern or list of patterns | no conditions | All must hold |
| `action` | `allow`, `ask`, `deny` | required | What happens when this is the first rule that applies |
| `effect` | `read`, `write`, `readwrite` | `readwrite` | Whether the call reads from the resource it touches, writes to it, or both |
| `source` | `trusted`, `untrusted` | `untrusted` | `untrusted`: the result contains text written by outsiders (issues, comments, PRs) |
| `impact` | `low`, `high` | `high` | `high`: needs a person once the session has read outsider text |
| `note` | text | — | Ignored; for people |

**Every omitted attribute takes its safe value.** A rule written for a new tool without `effect`, `source` or `impact` is treated as reading and writing, untrusted and high impact.

Unknown keys are errors, so a typo like `whne:` makes the whole file fail to load rather than silently dropping a condition. A file that fails to load is never used; the previous rules stay in force.

## Patterns

| Pattern | Matches |
|---|---|
| `**` | any characters, including `/` |
| `*` | any characters except `/` |
| `?` | one character except `/` |
| anything else | itself, exactly (case-sensitive) |

There are no escapes or character classes. Patterns match the whole string: `main` does not match `main2`.

## Conditions (`when`)

```yaml
when: { branch: [main, master], path: "**.github/**" }
```

- A condition looks at **every value of that argument anywhere in the call**. `path` finds the `path` of `create_or_update_file` and also each `files[].path` of `push_files`. Numbers and booleans are compared as their JSON text (`7`, `true`).
- How it counts depends on the rule's action, always in the safe direction:

| Rule action | The condition holds when … |
|---|---|
| `deny`, `ask` | the argument is **missing**, or **any** of its values matches |
| `allow` | the argument is present and **every** value matches |

So a push touching one workflow file among many hits an `ask` rule for `.github/**`, and a conditional `allow` only applies when all files qualify. A call with no `branch` counts as `main` for a deny rule (GitHub writes to the default branch when no branch is given).

Prefer allowlists for arguments with a fixed set of values. For reviews, allow `event: [COMMENT, REQUEST_CHANGES]` and deny the rest, rather than denying `APPROVE`: an allowlist also catches `approve` or values you didn't think of.

## Servers: resources and capabilities

`servers` describes each connection. First match wins; a server you don't list names no resource and has no capabilities.

```yaml
servers:
  - name: github
    resource: { keys: [owner, repo] }        # join these arguments with "/"
    capabilities:
      send_message: [add_issue_comment, issue_write]
      write_data:   [push_files, create_or_update_file, delete_file]
  - name: mail
    resource: { label: private }             # every call touches data at this label
    capabilities:
      send_message: "send_*"
```

- `resource` says how the server names the thing a call touches. `keys` joins those top-level arguments with `/` and matches the result against `resources`. `label` gives every call on that server the same label — use it for a server with no per-call resource (a mailbox, a scanner), where treating each call as unknown would push the session to the highest label on its first read.
- `capabilities` says what the server's tools do. Patterns match the **tool** name, not `server.tool`.

### The capability vocabulary

Twelve names, and only these. A name outside the list is an error, so a typo can't become a rule that silently never fires.

`network_scan` · `remote_access` · `packet_forge` · `malware_exec` · `service_disrupt` · `audit_tamper` · `guard_config_write` · `send_message` · `automated_decision` · `operate_physical_system` · `read_data` · `write_data`

A rule that names a capability reaches only the tools a server declared for it (`capability_needs_declaration`). So `{ capability: send_message, action: ask }` at the top of a rule file catches the tools your connections say are sends, and nothing else — it cannot reach a server that never said it sends anything.

## Resources and labels

- `labels` lists the confidentiality levels, lowest first.
- A call's resource is named by its server's `resource` entry: nothing is assumed about a connection you haven't declared. Names and `resources` patterns are compared **lowercased**, because many services treat names case-insensitively. The first matching entry gives the label.
- If the call names no resource (for example a search), or no entry matches: **reading** counts as the highest label and **writing** counts as the lowest. List every resource the agent should write to after reading private data.
