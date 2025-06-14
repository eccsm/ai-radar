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
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Production stage - final image
FROM base as production

# _core module will be handled by PYTHONPATH and volume mount in docker-compose

# Copy the critical files by name
COPY main.py /app/main.py
COPY requirements.txt /app/requirements.txt

# Create _core directory 
RUN mkdir -p /app/_core

# Command to run the agent
CMD ["python", "main.py"]

# Development stage - this will be used when target: development is specified
FROM base AS development

# In development mode, we don't copy the code
# It will be mounted as a volume from the host
# This allows for live code editing

# Create _core directory 
RUN mkdir -p /app/_core

# Command to run the agent in development mode
CMD ["python", "main.py"]