# Fetcher Agent Dockerfile
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
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM base AS production

# _core module will be handled by PYTHONPATH and volume mount in docker-compose

# VERY explicitly copy the critical files by name
RUN echo "--- Listing build context (./agents/fetcher/) ---" && ls -la . && echo "--- End of listing ---"
COPY ./main.py /app/main.py
COPY test.py /app/test.py
COPY requirements.txt /app/requirements.txt
COPY healthz.py /app/healthz.py

# Create _core directory and copy its contents
RUN mkdir -p /app/_core

# Add hvac for Vault integration
RUN pip install hvac

# Debug info
RUN ls -la /app
RUN echo "PYTHONPATH=$PYTHONPATH"

# Command to run the agent
CMD ["python", "main.py"]

# Development stage - this will be used when target: development is specified
FROM base AS development

# In development mode, we don't copy the code
# It will be mounted as a volume from the host
# This allows for live code editing

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${HEALTH_PORT:-8000}/health || exit 1

# Command to run the agent in development mode
CMD ["python", "main.py"]