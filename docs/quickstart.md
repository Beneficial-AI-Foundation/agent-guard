# Quickstart

## 1. Install

```bash
uv tool install agentguard     # or pipx install agentguard, or the Docker image (phase 5)
```

Until releases exist, install from a checkout: `make proofs && uv tool install .` and set `AGENTGUARD_WORKER` to `lean/.lake/build/bin/guard-worker`.

## 2. Register the GitHub App AgentGuard signs in with (once per organisation)

AgentGuard signs in to GitHub with the **device flow**: you open github.com/login/device and type a short code. That needs a GitHub App (recommended) or OAuth App with device flow enabled.

1. GitHub → Settings → Developer settings → **GitHub Apps → New GitHub App** (under the organisation that owns the repositories).
2. Name it (e.g. "AgentGuard"), set any homepage URL, untick **Webhook → Active**.
3. Tick **Enable Device Flow**.
4. Repository permissions: **Contents** read & write, **Issues** read & write, **Pull requests** read & write, **Actions** read & write (only if agents may run workflows), **Metadata** read.
5. Create it, then **Install App** on only the repositories the agent should touch (for the demo: `demo-public` and `demo-private`).
6. Copy the **Client ID** into `~/.agentguard/github/.env` as `AGENTGUARD_GITHUB_CLIENT_ID=…`.

Why a GitHub App: its tokens only reach the repositories it is installed on, and expire after 8 hours (AgentGuard refreshes them). An OAuth App's `repo` scope reaches every repository you can.

## 3. Create the profile and sign in

```bash
agentguard init github
agentguard login            # if init skipped it
```

```
Open https://github.com/login/device and enter code  WDJB-MJHT
✓ Signed in as @you (scopes: app permissions); token stored in the keyring store
```

The token is kept in the OS keychain (or, in Docker, an encrypted file keyed by `AGENTGUARD_TOKEN_KEY`). It is never written to `mcp.json` or the logs.

## 4. Point your agent at AgentGuard

```bash
agentguard connect vscode        # user mcp.json; --workspace DIR for a project's .vscode/mcp.json
agentguard connect claude-code   # user scope through the claude CLI; --workspace DIR for .mcp.json
agentguard connect cursor
agentguard doctor
```

`connect` adds this entry and sets aside any entry that reaches the same server directly (a backup of the file is kept):

```json
{ "servers": { "agentguard": { "type": "stdio", "command": "agentguard", "args": ["stdio", "--profile", "~/.agentguard/github"] } } }
```

## 5. Adjust the rules, watch and approve

- Edit `~/.agentguard/github/rules.yaml` ([reference](rules.md)). It reloads on save; a file Lean rejects is never loaded and the previous rules stay.
- `agentguard try "push_files owner=you repo=demo-public branch=main"` shows the verdict without calling anything.
- The console (link printed at start) shows every call and the approval cards. Start in `--mode audit` (log "would deny" but forward everything), then switch to `enforce`.
