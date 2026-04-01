# ---- Builder Stage ----
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir --prefix=/install .

# ---- Runtime Stage ----
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install runtime dependencies + Node.js for Claude CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get purge -y gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* /root/.npm \
    && groupadd -r rafraf && useradd -r -g rafraf -d /app -m rafraf

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY app/ ./app/

# Create claude home directory for credential mount
RUN mkdir -p /home/rafraf/.claude && chown -R rafraf:rafraf /app /home/rafraf/.claude

USER rafraf

# Claude CLI non-interactive mode
ENV CI=1
ENV DISABLE_AUTOUPDATER=1
ENV CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Run with uvicorn - 2 workers for small deployment
CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--no-access-log"]
