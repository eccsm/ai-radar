FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir nats-py asyncio

# Copy script
COPY trigger_fetcher.py .

# Run script
CMD ["python", "trigger_fetcher.py"]
