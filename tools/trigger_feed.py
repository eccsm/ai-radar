#!/usr/bin/env python3
"""
Trigger Feed Script for AI Radar
This script publishes a message to the NATS subject to trigger RSS feed fetching.
It's designed to run in a Docker container as part of the AI Radar system.
"""

import asyncio
import os
import json
import time
import sys
from datetime import datetime
import nats
from nats.js.api import StreamConfig
from nats.errors import TimeoutError, NoServersError

# Configuration
NATS_URLS = [
    "nats:4222",               # Docker service name
    "host.docker.internal:4222", # For Docker Desktop on Windows/Mac
    "localhost:4222"           # Fallback
]
NATS_SUBJECT = "ai-radar.tasks.rss_fetch"  # Using consistent task namespacing
NATS_STREAM = "ai-radar-tasks"

async def setup_nats():
    """Connect to NATS and ensure stream exists"""
    # Try multiple NATS URLs with fallbacks
    nc = None
    for url in NATS_URLS:
        try:
            print(f"Attempting to connect to NATS at {url}...")
            nc = await nats.connect(url)
            print(f"Connected to NATS at {url}")
            break
        except (TimeoutError, NoServersError) as e:
            print(f"Failed to connect to NATS at {url}: {e}")
            continue
    
    if nc is None:
        print("Failed to connect to any NATS server")
        sys.exit(1)
    
    # Create JetStream context
    js = nc.jetstream()
    
    # Ensure stream exists
    try:
        # Check if stream exists
        await js.stream_info(NATS_STREAM)
        print(f"Stream {NATS_STREAM} exists")
    except nats.js.errors.NotFoundError:
        # Create stream if it doesn't exist
        print(f"Creating stream {NATS_STREAM}")
        await js.add_stream(
            StreamConfig(
                name=NATS_STREAM,
                subjects=[f"{NATS_SUBJECT}"],
                retention="limits",
                max_msgs=10000,
                max_bytes=1_073_741_824,  # 1GB
                discard="old",
                storage="memory"
            )
        )
    
    return nc, js

async def trigger_feed():
    """Publish message to trigger feed fetching"""
    nc, js = await setup_nats()
    
    try:
        # Create message payload similar to what the scheduler would send
        message = {
            "task_id": f"manual-trigger-{int(time.time())}",
            "timestamp": datetime.utcnow().isoformat(),
            "action": "fetch_rss",
            "source": "trigger-script"
        }
        
        # Publish message
        print(f"Publishing message to {NATS_SUBJECT}: {message}")
        ack = await js.publish(NATS_SUBJECT, json.dumps(message).encode())
        print(f"Message published: stream={ack.stream}, sequence={ack.seq}")
        
        # Wait briefly to ensure message is processed
        await asyncio.sleep(1)
    finally:
        # Close NATS connection
        await nc.close()
        print("NATS connection closed")

if __name__ == "__main__":
    print("Starting RSS feed trigger script")
    
    # Run once immediately
    asyncio.run(trigger_feed())
    
    # Exit with success
    print("Feed trigger completed successfully")
    sys.exit(0)
