# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.8.13 AS uv

FROM python:3.12.11-slim-bookworm AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /srv/api
COPY --from=uv /uv /uvx /usr/local/bin/
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

FROM python:3.12.11-slim-bookworm AS runtime
ENV PATH="/srv/api/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    API_HOST=0.0.0.0 \
    API_PORT=8000
WORKDIR /srv/api
RUN groupadd --system --gid 10001 support-agent \
    && useradd --system --uid 10001 --gid support-agent --home-dir /srv/api support-agent \
    && mkdir -p /srv/api/.data/uploads \
    && chown -R support-agent:support-agent /srv/api
COPY --from=builder --chown=support-agent:support-agent /srv/api/.venv ./.venv
COPY --chown=support-agent:support-agent apps/api/alembic.ini ./
COPY --chown=support-agent:support-agent apps/api/alembic ./alembic
COPY --chown=support-agent:support-agent apps/api/app ./app
COPY --chown=support-agent:support-agent apps/api/configure_runtime_role.py ./
USER support-agent
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
