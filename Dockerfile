FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable


FROM python:3.13-slim-bookworm AS run

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 1000 app

WORKDIR /app

COPY --from=build --chown=app:app /app/.venv /app/.venv

USER app

EXPOSE 8000

CMD ["publix-sorter", "serve", "--host", "0.0.0.0", "--port", "8000"]
