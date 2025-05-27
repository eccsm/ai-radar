#!/usr/bin/env python
"""
Trigger Fetcher Script
This script triggers the fetcher agent to fetch articles from RSS feeds.
"""
import asyncio
import json
import nats
from datetime import datetime
import os

# Environment variables
NATS_URL = os.getenv("NATS_URL", "nats://nats:4222")

# Define RSS feeds to add
RSS_FEEDS = [
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
    {"name": "Wired", "url": "https://www.wired.com/feed/rss"},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/"},
    {"name": "VentureBeat", "url": "https://venturebeat.com/feed/"},
    {"name": "ArsTechnica", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
    {"name": "AI News", "url": "https://artificialintelligence-news.com/feed/"}
]

async def main():
    print(f"Connecting to NATS at {NATS_URL}...")
    
    # Connect to NATS with retry logic
    max_retries = 5
    retry_delay = 2  # seconds
    
    for attempt in range(1, max_retries + 1):
        try:
            # Connect to NATS
            nc = await nats.connect(
                NATS_URL,
                connect_timeout=10.0,
                reconnect_time_wait=2.0,
                max_reconnect_attempts=5
            )
            js = nc.jetstream()
            print("Successfully connected to NATS")
            break
        except Exception as e:
            if attempt == max_retries:
                print(f"Failed to connect to NATS after {max_retries} attempts: {e}")
                return
            print(f"Connection attempt {attempt} failed: {e}. Retrying in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)
    
    # Ensure stream exists
    try:
        await js.add_stream(
            name="ai-radar",
            subjects=["ai-radar.>"],
            storage="file",
            max_msgs=100000,
        )
        print("Stream created or already exists")
    except Exception as e:
        print(f"Stream exists or error: {e}")
    
    # Publish tasks for each RSS feed
    for feed in RSS_FEEDS:
        # Create a message payload
        payload = {
            "url": feed["url"],
            "name": feed["name"],
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # Publish the message to trigger fetcher
            await js.publish(
                "ai-radar.tasks.rss_fetch",
                json.dumps(payload).encode()
            )
            print(f"Published task for: {feed['name']}")
        except Exception as e:
            print(f"Failed to publish task for {feed['name']}: {e}")
        
        # Small delay between tasks
        await asyncio.sleep(1)
    
    # Close NATS connection
    await nc.close()
    print("Done! The fetcher agent should now process these feeds.")

if __name__ == "__main__":
    asyncio.run(main())
