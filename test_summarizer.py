#!/usr/bin/env python
import asyncio
import nats
import json
from datetime import datetime

async def main():
    # Connect to NATS
    print("Connecting to NATS...")
    nc = await nats.connect("nats://nats:4222")
    js = nc.jetstream()
    
    # Create a test message that simulates what the fetcher would send
    # This is a very simple test message with minimal required fields
    test_message = {
        "title": "Test Article",
        "url": "https://example.com/test-article",
        "published_at": datetime.now().isoformat(),
        "content_key": "test-content.txt",  # This won't exist in S3 but we'll handle the error
        "author": "Test Author",
        "source_name": "Test Source",
        "source_url": "https://example.com",
        "timestamp": datetime.now().isoformat()
    }
    
    # Publish directly to the summarizer's subject
    print(f"Publishing test message to ai-radar.tasks.summarize")
    await js.publish("ai-radar.tasks.summarize", json.dumps(test_message).encode())
    
    print("Test message published. Check summarizer logs for processing.")
    
    # Close the connection
    await nc.drain()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
