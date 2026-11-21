"""AgentGuard: an MCP gateway whose decisions are proved in Lean 4.

This package (the `src/` folder, installed as `agentguard`) moves bytes between
the agent, the Lean decision worker and the upstream MCP server. It never
decides allow, ask or deny itself: every verdict comes from `lean/`.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("agentguard")
except PackageNotFoundError:  # running from a checkout without installing
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
