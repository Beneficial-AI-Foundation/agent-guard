from __future__ import annotations

from pathlib import Path

import pytest

from agentguard.errors import ProfileError, RulesError
from agentguard.profile import loader, mcp_json, rules
from agentguard.profile.env import parse_dotenv, substitute


def test_dotenv() -> None:
    env = parse_dotenv(
        "# comment\nA=1\nexport B = two words # trailing\nC='single # kept'\n"
        'D="dq\\nline"\n\nE=\n'
    )
    assert env == {"A": "1", "B": "two words", "C": "single # kept", "D": "dq\nline", "E": ""}


def test_dotenv_rejects_garbage() -> None:
    with pytest.raises(ProfileError, match="line 1"):
        parse_dotenv("not a pair")


def test_substitute() -> None:
    env = {"TOKEN": "t", "GITHUB_TOKEN": "g"}
    b = {"workspaceFolder": "/w"}
    assert substitute("Bearer ${TOKEN}", env, b) == "Bearer t"
    assert substitute("${env:TOKEN}-${workspaceFolder}", env, b) == "t-/w"
    assert substitute("${input:github_token}", env, b) == "g"
    with pytest.raises(ProfileError, match="MISSING is not set"):
        substitute("${MISSING}", env, b)
    with pytest.raises(ProfileError, match="EMPTY is not set"):  # `GITHUB_PAT=` left blank
        substitute("Bearer ${env:EMPTY}", {"EMPTY": ""}, b)
    with pytest.raises(ProfileError, match="add NOPE"):
        substitute("${input:nope}", env, b)


VSCODE = """{
  // VS Code style, with comments and trailing commas
  "inputs": [{"type": "promptString", "id": "github_token", "password": true}],
  "servers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": {"Authorization": "Bearer ${input:github_token}"},
    },
    "local": {"command": "docker", "args": ["run", "-i", "ghcr.io/x"], "env": {"T": "${env:T}"}},
    /* a guarded entry pasted by mistake */
    "agentguard": {"command": "agentguard", "args": ["stdio"]},
  },
}"""


def test_mcp_json_vscode() -> None:
    servers = mcp_json.parse(VSCODE)
    env = {"GITHUB_TOKEN": "abc", "T": "t"}
    got = [
        mcp_json.server_from(n, r, env, Path("/p"))
        for n, r in servers.items()
        if not mcp_json.is_agentguard(n, r)
    ]
    assert [s.name for s in got] == ["github", "local"]
    assert got[0].kind == "http"
    assert got[0].headers["Authorization"] == "Bearer abc"
    assert got[1].kind == "stdio" and got[1].env == {"T": "t"}


def test_mcp_json_claude_format() -> None:
    servers = mcp_json.parse('{"mcpServers": {"github": {"url": "https://x/mcp"}}}')
    s = mcp_json.server_from("github", servers["github"], {}, Path("/p"))
    assert s.kind == "http" and s.url == "https://x/mcp" and s.headers == {}


def test_mcp_json_errors() -> None:
    with pytest.raises(ProfileError, match="servers"):
        mcp_json.parse("{}")
    with pytest.raises(ProfileError, match="SSE"):
        mcp_json.server_from("x", {"type": "sse", "url": "u"}, {}, Path("/p"))
    with pytest.raises(ProfileError, match="command"):
        mcp_json.server_from("x", {"type": "stdio"}, {}, Path("/p"))


def test_strip_jsonc_keeps_strings() -> None:
    text = '{"a": "// not a comment", "b": "/* nor this */", "c": [1,],}'
    assert mcp_json.parse('{"servers": ' + text + "}") == {
        "a": "// not a comment",
        "b": "/* nor this */",
        "c": [1],
    }


def test_rules_yaml() -> None:
    pol = rules.to_json("labels: [public]\nrules:\n  - {tool: x, action: deny}\n")
    assert pol == {"labels": ["public"], "rules": [{"tool": "x", "action": "deny"}]}
    assert rules.policy_hash(pol) == rules.policy_hash(dict(reversed(pol.items())))


def test_rules_yaml_duplicate_key() -> None:
    with pytest.raises(RulesError, match="not valid YAML") as e:
        rules.to_json("rules:\n  - {tool: x, action: deny, action: allow}\n")
    assert "duplicate key 'action'" in str(e.value)


def test_rules_yaml_not_mapping() -> None:
    with pytest.raises(RulesError, match="mapping"):
        rules.to_json("- a\n- b\n")


def test_load_profile(tmp_path: Path) -> None:
    (tmp_path / "mcp.json").write_text(
        '{"servers": {"github": {"url": "https://x", "headers": '
        '{"Authorization": "Bearer ${TOKEN}"}}}}'
    )
    (tmp_path / "rules.yaml").write_text("labels: [public]\nrules: []\n")
    (tmp_path / ".env").write_text("TOKEN=from-dotenv\n")
    p = loader.load(tmp_path)
    assert p.server("github").headers["Authorization"] == "Bearer from-dotenv"
    assert p.policy == {"labels": ["public"], "rules": []}
    with pytest.raises(ProfileError):
        p.server("nope")


def test_load_profile_missing(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match="not found"):
        loader.load(tmp_path / "nope")
