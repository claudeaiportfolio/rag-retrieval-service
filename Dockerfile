FROM python:3.12-slim AS base

ARG SERVICE
ENV SERVICE=${SERVICE}

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY uv.lock* ./

RUN uv sync --no-dev --no-editable || uv sync --no-dev --no-editable --no-lock

COPY src/ ./src/

ENV PYTHONPATH=/app/src
ENV PATH="/app/.venv/bin:${PATH}"

RUN useradd --system --uid 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 8080

# SERVICE selects the entrypoint module at runtime so a single image source
# produces the four service images via build-arg.
ENV SERVICE=${SERVICE}
CMD ["/bin/sh", "-c", "\
    case \"$SERVICE\" in \
      upload-api) exec uvicorn upload_api.main:app --host 0.0.0.0 --port 8080 ;; \
      retrieval-api) exec uvicorn retrieval_api.main:app --host 0.0.0.0 --port 8080 ;; \
      mcp-server) exec python -m mcp_server.main ;; \
      embedding-worker) exec python -m embedding_worker.main ;; \
      *) echo \"unknown SERVICE: $SERVICE\"; exit 64 ;; \
    esac"]
