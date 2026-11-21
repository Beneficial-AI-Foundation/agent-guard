#!/usr/bin/env bash
# Builds a platform wheel with the (already built) Lean worker inside.
#   scripts/build_wheels.sh manylinux_2_28_x86_64
set -euo pipefail
PLAT="${1:?usage: build_wheels.sh PLATFORM_TAG}"
cd "$(dirname "$0")/.."
mkdir -p src/bin
install -m 755 lean/.lake/build/bin/guard-worker src/bin/guard-worker
strip src/bin/guard-worker 2>/dev/null || strip -x src/bin/guard-worker
rm -rf dist && uv build --wheel
# The worker is native code, so the wheel is platform-specific, not py3-none-any.
uvx --from wheel wheel tags --remove --python-tag py3 --abi-tag none --platform-tag "$PLAT" dist/*.whl
ls dist
