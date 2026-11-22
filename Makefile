.PHONY: check proofs test live lint fmt sync clean

check: proofs lint test

sync:
	uv sync --locked

proofs:
	scripts/check_proofs.sh

test: sync
	uv run pytest

# The six stories against real GitHub: make live OWNER=your-test-org
live: sync
	AGENTGUARD_LIVE_OWNER=$(OWNER) uv run pytest tests/live -v

lint: sync
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy -p agentguard
	uv run mypy tests

fmt:
	uv run ruff format .
	uv run ruff check --fix .

clean:
	rm -rf dist build .pytest_cache .mypy_cache .ruff_cache lean/.lake/build
