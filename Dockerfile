# syntax=docker/dockerfile:1
# Host OS: Ubuntu 26.04 LTS; Python runtime image is independently maintained.
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --disable-pip-version-check --no-cache-dir --no-compile ".[mcp]"

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
ARG VCS_REF=unknown
LABEL org.opencontainers.image.source="https://github.com/lqepoch/Mechanical_Patent" \
      org.opencontainers.image.description="Mechanical Patent local-only MCP service" \
      org.opencontainers.image.licenses="See repository NOTICE" \
      org.opencontainers.image.revision="${VCS_REF}"
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATENT_MCP_WORKSPACE=/data \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache
# Pandoc is a required backend for the project's LaTeX -> DOCX/HTML/Markdown exports.
# Do not install a TeX/PDF compiler in the online MCP service.
RUN apt-get update && apt-get install -y --no-install-recommends pandoc \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /opt/venv /opt/venv
RUN groupadd --gid 10001 patent && \
    useradd --uid 10001 --gid 10001 --home-dir /tmp --no-create-home --shell /usr/sbin/nologin patent && \
    mkdir -p /data && chown 10001:10001 /data
WORKDIR /data
USER 10001:10001
EXPOSE 8765
# TCP liveness only; authorization and tool behavior are covered by separate tests.
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import socket; s=socket.create_connection(('127.0.0.1', 8765), timeout=2); s.close()" || exit 1
ENTRYPOINT ["python", "-m", "mechanical_patent.mcp_server"]
CMD ["--transport", "streamable-http", "--host", "127.0.0.1", "--port", "8765", "--workspace", "/data"]
