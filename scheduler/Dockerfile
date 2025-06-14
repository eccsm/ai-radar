FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv

# Create a non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set ownership to non-root user
RUN chown -R appuser:appuser /app

# Use virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Switch to non-root user
USER appuser

# Health check - using HTTP endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

# Command to run the scheduler
CMD ["python", "main.py"]
