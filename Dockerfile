# syntax=docker/dockerfile:1
# AgentGuard: build the proved Lean worker, bundle it in the wheel, run as non-root.

# 1. Lean: build the worker and check every proof (fails the build on sorry/axioms)
FROM debian:bookworm-slim AS lean
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates git binutils \
    && rm -rf /var/lib/apt/lists/*
RUN curl -sSfL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \
    | sh -s -- -y --default-toolchain none
ENV PATH="/root/.elan/bin:${PATH}"
WORKDIR /src/lean
COPY lean/lean-toolchain lean/lakefile.toml lean/lake-manifest.json ./
RUN elan toolchain install "$(cat lean-toolchain)"
COPY lean/ ./
RUN lake build --wfail && lake build GuardTest --wfail && lake exe check-axioms \
    && strip .lake/build/bin/guard-worker

# 2. Python: the wheel, with the worker inside
FROM python:3.12-slim AS wheel
COPY --from=ghcr.io/astral-sh/uv:0.11.31 /uv /usr/local/bin/uv
WORKDIR /src
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
COPY --from=lean /src/lean/.lake/build/bin/guard-worker src/bin/guard-worker
RUN uv build --wheel --out-dir /dist

# 3. Runtime
FROM python:3.12-slim
LABEL org.opencontainers.image.title="AgentGuard" \
      org.opencontainers.image.description="MCP gateway with allow/ask/deny decisions proved in Lean 4"
RUN useradd --create-home --uid 10001 agentguard && mkdir /data && chown agentguard /data
COPY --from=wheel /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl
USER agentguard
ENV AGENTGUARD_HOME=/data \
    AGENTGUARD_TOKEN_STORE=file \
    AGENTGUARD_HOST=0.0.0.0 \
    AGENTGUARD_CONSOLE_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8080 7070
HEALTHCHECK --interval=30s --timeout=3s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')" || exit 1
ENTRYPOINT ["agentguard"]
CMD ["serve", "--profile", "/data/github"]
