#!/usr/bin/env python
"""
RSS Feed Trigger Script for AI Radar
Manually triggers RSS feed fetching by publishing tasks to NATS
"""
import asyncio
import json
import os
import sys

# Try to import nats-py, install if missing
try:
    import nats
except ImportError:
    print("nats-py not found. Please install it with: pip install nats-py")
    sys.exit(1)

async def main():
    # Try different NATS URLs to handle both Docker and local environments
    nats_urls = [
        os.getenv("NATS_URL", "nats://localhost:4222"),  # Try environment variable first
        "nats://localhost:4222",                         # Local development
        "nats://127.0.0.1:4222"                          # Alternative local address
    ]
    
    # Try each URL until one works
    connected = False
    nc = None
    js = None
    
    for url in nats_urls:
        print(f"Trying to connect to NATS at {url}...")
        max_retries = 2  # Fewer retries per URL since we have multiple URLs to try
        
        for attempt in range(1, max_retries + 1):
            try:
                print(f"Connection attempt {attempt}/{max_retries}")
                # Connect to NATS with timeout and reconnect options
                nc = await nats.connect(
                    url,
                    connect_timeout=5.0,  # Shorter timeout to try other URLs faster
                    reconnect_time_wait=1.0,
                    max_reconnect_attempts=3
                )
                js = nc.jetstream()
                print(f"Successfully connected to NATS at {url}")
                connected = True
                break
            except Exception as e:
                print(f"Connection attempt to {url} failed: {e}")
                if attempt < max_retries:
                    print(f"Retrying in 1 second...")
                    await asyncio.sleep(1)
        
        if connected:
            break
    
    if not connected:
        print("Failed to connect to NATS on any available URL. Please ensure NATS is running.")
        return
    
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
        print(f"Stream setup: {e}")
        
        # List of AI news sources
        sources = [
            {
                "url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
                "name": "Wall Street Journal"
            },
            {
                "url": "https://www.wired.com/feed/tag/artificial-intelligence/latest/rss",
                "name": "Wired AI"
            },
            {
                "url": "https://news.mit.edu/topic/artificial-intelligence2-rss.xml",
                "name": "MIT AI News"
            },
            {
                "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
                "name": "TechCrunch AI"
            }
        ]
        
        # Publish each source
        success_count = 0
        for source in sources:
            try:
                # Create a message payload with timestamp
                payload = {
                    "url": source["url"],
                    "name": source["name"],
                    "timestamp": asyncio.get_running_loop().time(),
                    "source_id": None  # For compatibility with scheduler format
                }
                
                # Publish to JetStream for persistence
                await js.publish(
                    "ai-radar.tasks.rss_fetch",
                    json.dumps(payload).encode()
                )
                print(f"Published task for: {source['name']}")
                success_count += 1
            except Exception as e:
                print(f"Failed to publish task for {source['name']}: {e}")
            
            # Small delay between tasks
            await asyncio.sleep(1)
        
        # Close the connection
        print(f"Successfully published {success_count}/{len(sources)} sources")
        print("Closing connection...")
        await nc.drain()
        print("Done! The fetcher agent should now process these feeds.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProcess interrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
