# Testing

| Level | Question | How |
|---|---|---|
| Proofs | Does the decision have the safety properties? | `scripts/check_proofs.sh`: Lean build with warnings as errors, `#guard` examples, `check-axioms` |
| Lean vs. reference | Does the code that runs match an independent copy? | `tests/property/`: 10,000 random rule files and call sequences (`AGENTGUARD_PROPERTY_CASES`, `AGENTGUARD_PROPERTY_SEED`) |
| Unit and integration | Does the gateway obey the verdicts, fail closed, and log safely? | `tests/unit/`, `tests/integration/`: the echo server (never GitHub) in-process, over stdio and over HTTP |
| Stories | Do the GitHub rules do what the demo says? | `examples/github/tests/` and `agentguard demo`: the six stories against the mock GitHub server |
| Real GitHub (phase 4) | Is it enforced against the live server? | `tests/live/`: scripted calls through the gateway to `demo-public` / `demo-private`, then REST API checks; also checks every tool the rules name exists on the live server |
| Real agent (phase 4) | Does it hold with a real agent? | VS Code or Claude Code given the prompts in [session-history.md](session-history.md) §6 |

`make check` runs everything up to the stories. CI runs the same, with the Python job using the worker the proofs job built; tests that need the worker fail instead of skipping there (`AGENTGUARD_REQUIRE_WORKER=1`).

## Running the live tests (phase 4)

The full runbook, including the GitHub App and the real-agent prompts, is [phase4.md](phase4.md).

1. Create the test repositories (a throwaway org is best): `scripts/setup_test_repos.sh OWNER`.
2. Register the GitHub App and install it on those two repositories only ([quickstart](quickstart.md) step 2).
3. `agentguard init github --profile ~/agentguard-live` and `agentguard login ~/agentguard-live`.
4. Run them. The extra token is used only by the checks (REST API), never by the agent:

```bash
AGENTGUARD_LIVE=1 AGENTGUARD_LIVE_PROFILE=~/agentguard-live AGENTGUARD_LIVE_OWNER=OWNER \
AGENTGUARD_LIVE_TOKEN=$(gh auth token) uv run pytest tests/live -v
```

`.github/workflows/live.yml` runs the same nightly and on demand, from secrets.
