# Summariser Agent Dockerfile

# Base image for both production and development
FROM python:3.11-slim as base

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
COPY agents/summariser/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create directory structure
RUN mkdir -p /app/agents/summariser
RUN mkdir -p /app/_core

# Production stage - final image
FROM base as production

# Copy shared _core module
COPY _core/ /app/_core/

# Copy agent-specific code
COPY agents/_core/ /app/agents/_core/
COPY agents/summariser/ /app/agents/summariser/

# Set PYTHONPATH to include app directory
ENV PYTHONPATH=/app

# Command to run the agent
CMD ["python", "/app/agents/summariser/main.py"]

# Development stage
FROM base as development

# In development mode, we don't copy files - they're mounted as volumes
# This allows for live code changes without rebuilding the container

# Set PYTHONPATH to include app directory
ENV PYTHONPATH=/app

# Command to run the agent
CMD ["python", "/app/agents/summariser/main.py"]