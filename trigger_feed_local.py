#!/usr/bin/env python
"""
Trigger Feed Script (Local Version)
This script triggers the fetcher agent to fetch articles from RSS feeds.
Designed to run directly on the host machine, not in Docker.
"""
import asyncio
import json
import nats
import os
import sys
from datetime import datetime

async def main():
    # Use localhost for direct connection from Windows to Docker
    nats_url = "nats://localhost:4222"
    
    print(f"Connecting to NATS at {nats_url}...")
    
    try:
        # Connect to NATS with timeout and reconnect options
        nc = await nats.connect(
            nats_url,
            connect_timeout=10.0,
            reconnect_time_wait=2.0,
            max_reconnect_attempts=3
        )
        js = nc.jetstream()
        print("Successfully connected to NATS")
        
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
            print(f"Stream setup note: {e}")
        
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
                    "source_id": None,  # For compatibility with scheduler format
                    "timestamp": datetime.now().isoformat()
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
