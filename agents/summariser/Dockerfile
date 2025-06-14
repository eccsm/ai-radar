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
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Production stage - final image
FROM base as production

# _core module will be handled by PYTHONPATH and volume mount in docker-compose

# VERY explicitly copy the critical files by name
COPY main.py /app/main.py
COPY requirements.txt /app/requirements.txt
COPY healthz.py /app/healthz.py

# Create _core directory 
RUN mkdir -p /app/_core

# Set PYTHONPATH to include app directory
# This will be overridden by docker-compose if needed for dev volume mounts
ENV PYTHONPATH=/app

# Add hvac for Vault integration
RUN pip install hvac

# Debug info
RUN echo "Content of app directory:" && ls -la /app
RUN echo "PYTHONPATH=$PYTHONPATH"

# Command to run the agent
CMD ["python", "main.py"]

# Development stage
FROM base as development

# In development mode, we don't copy files - they're mounted as volumes
# This allows for live code changes without rebuilding the container

# Set PYTHONPATH to include app directory
ENV PYTHONPATH=/app

# Command to run the agent
CMD ["python", "main.py"]