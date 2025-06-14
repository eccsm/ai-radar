# Base stage with common dependencies
FROM python:3.11-slim AS base

# Set the working directory in the container
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Development stage - includes debugging tools and mounts code at runtime
FROM base AS development
RUN pip install debugpy

# Copy the agent code
COPY . .

# Command to run the application
CMD ["python", "main.py"]

# Production stage - minimal and secure
FROM base AS production

# Copy the agent code
COPY . .

# Command to run the application
CMD ["python", "main.py"]
