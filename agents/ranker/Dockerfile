# Ranker Agent Dockerfile
FROM python:3.11-slim AS base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements first for better caching
COPY agents/ranker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create directory structure
RUN mkdir -p /app/_core

# Production stage
FROM base AS production

# Copy shared _core module
COPY _core/ /app/_core/
RUN pip install --no-cache-dir /app/_core/

# Copy agent-specific code
COPY agents/ranker/ .

# Command to run the agent
CMD ["python", "main.py"]

# Development stage - this will be used when target: development is specified
FROM base AS development

# In development mode, we don't copy the code
# It will be mounted as a volume from the host
# This allows for live code editing

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${HEALTH_PORT:-8002}/health || exit 1

# Command to run the agent in development mode
CMD ["python", "main.py"]