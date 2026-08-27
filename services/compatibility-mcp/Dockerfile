FROM python:3.12-slim@sha256:7a8b475003c4fe15a2cd4e55e5cfc2f3560bdc9333d624f24cdd6d4340fd7a17

COPY --from=ghcr.io/astral-sh/uv:0.11.27 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH=/app/src

EXPOSE 4100
CMD ["python", "-m", "airstrong_compatibility_mcp.server"]
