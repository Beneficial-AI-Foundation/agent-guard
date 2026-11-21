.PHONY: check proofs test lint fmt sync clean

check: proofs lint test

sync:
	uv sync --locked

proofs:
	scripts/check_proofs.sh

test: sync
	uv run pytest

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
