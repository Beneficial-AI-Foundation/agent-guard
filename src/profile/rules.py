"""`rules.yaml` → JSON for Lean. Mechanical only: Lean validates and interprets it.

The one check here is that a YAML mapping has no duplicate keys (YAML would
otherwise keep the last one silently, e.g. a second `action:`)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from ..errors import RulesError


class _StrictLoader(yaml.SafeLoader):
    pass


def _mapping(loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate key {key!r}", key_node.start_mark
            )
        seen.add(key)
    return loader.construct_mapping(node, deep=deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def to_json(text: str, source: str = "rules.yaml") -> dict[str, Any]:
    try:
        data = yaml.load(text, Loader=_StrictLoader)  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as e:
        raise RulesError(f"{source} is not valid YAML", [str(e)]) from e
    if not isinstance(data, dict):
        raise RulesError(f"{source} must be a mapping with labels, repos and rules")
    try:
        json.dumps(data)
    except TypeError as e:  # dates and other non-JSON YAML types
        raise RulesError(f"{source} contains a value JSON can't hold", [str(e)]) from e
    return data


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RulesError(f"{path} not found")
    return to_json(path.read_text(encoding="utf-8"), str(path))


def policy_hash(policy: dict[str, Any]) -> str:
    """Stable hash of a rule file's content, for the audit log and console."""
    canon = json.dumps(policy, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()[:16]
