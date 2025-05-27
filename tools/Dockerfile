FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY tools/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy script
COPY tools/trigger_feed.py .

# Run script
CMD ["python", "trigger_feed.py"]
