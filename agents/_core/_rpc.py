"""
RPC Module
Thin wrapper around NATS for agent communication
"""
import json
import logging
import asyncio
from typing import Dict, Any, Optional, Callable
import nats
from nats.js.api import StreamConfig

class NatsClient:
    """
    NATS client for messaging between agents.
    """
    
    def __init__(self, url, logger=None):
        """Initialize the NATS client.
        
        Args:
            url: NATS URL (primary URL to try)
            logger: Logger instance
        """
        self.url = url
        self.nc = None
        self.js = None
        self.logger = logger or logging.getLogger(__name__)
        self.subscriptions = {}
        
        # Fallback URLs to try if the primary URL fails
        self.fallback_urls = [
            # Try Docker service name
            "nats://nats:4222",
            # Try localhost (for local development)
            "nats://localhost:4222",
            # Try host.docker.internal (for Docker Desktop)
            "nats://host.docker.internal:4222"
        ]
        
        # Ensure primary URL is not duplicated in fallbacks
        if self.url in self.fallback_urls:
            self.fallback_urls.remove(self.url)
        
        # Add the primary URL at the beginning
        self.fallback_urls.insert(0, self.url)
        
    async def connect(self, timeout=10.0):
        """Connect to NATS server with timeout.
        
        Args:
            timeout: Connection timeout in seconds
        """
        # Try each URL in order until one succeeds
        last_error = None
        for i, url in enumerate(self.fallback_urls):
            try:
                self.logger.info(f"Connecting to NATS at {url} (attempt {i+1}/{len(self.fallback_urls)}, timeout: {timeout}s)")
                self.nc = await nats.connect(
                    servers=[url],
                    reconnect_time_wait=2.0,
                    max_reconnect_attempts=5,
                    connect_timeout=timeout
                )
                self.js = self.nc.jetstream()
                
                # Try to ensure the ai-radar stream exists
                try:
                    await self.js.add_stream(
                        name="ai-radar",
                        subjects=["ai-radar.>"],
                        storage="file",
                        max_msgs=100000,
                    )
                except Exception as e:
                    self.logger.warning(f"Stream exists or error: {e}")
                
                self.logger.info(f"Successfully connected to NATS at {url}")
                return True
            except Exception as e:
                last_error = e
                self.logger.warning(f"Failed to connect to NATS at {url}: {e}")
                # Continue to the next URL
        
        # If we got here, all URLs failed
        self.logger.error(f"Failed to connect to any NATS server after {len(self.fallback_urls)} attempts")
        raise last_error or Exception("Failed to connect to any NATS server")
            
    async def close(self):
        """Close NATS connection."""
        if self.nc:
            await self.nc.close()
            self.logger.info("NATS connection closed")
            
    async def publish(self, subject: str, payload: Dict[str, Any]):
        """
        Publish a message to a subject.
        
        Args:
            subject (str): Subject to publish to
            payload (Dict[str, Any]): Message payload
        """
        max_retries = 5
        retry_delay = 2  # seconds
        
        for attempt in range(1, max_retries + 1):
            try:
                if not self.js:
                    if attempt == max_retries:
                        raise RuntimeError("Not connected to NATS after multiple attempts")
                    self.logger.warning(f"NATS not connected on publish attempt {attempt}. Trying to connect...")
                    try:
                        await self.connect()
                    except Exception as e:
                        self.logger.warning(f"Connection attempt {attempt} failed: {e}. Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                        continue
                
                await self.js.publish(
                    subject,
                    json.dumps(payload).encode()
                )
                self.logger.debug(f"Successfully published to {subject}")
                return
            except Exception as e:
                if attempt == max_retries:
                    self.logger.error(f"Failed to publish to {subject} after {max_retries} attempts: {e}")
                    raise
                self.logger.warning(f"Publish attempt {attempt} failed: {e}. Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            
    async def call(self, subject: str, payload: Dict[str, Any], timeout: float = 10.0) -> Dict[str, Any]:
        """
        Make a request and wait for a response.
        
        Args:
            subject (str): Subject to send request to
            payload (Dict[str, Any]): Request payload
            timeout (float): Timeout in seconds
            
        Returns:
            Dict[str, Any]: Response payload
        """
        max_retries = 5
        retry_delay = 2  # seconds
        
        for attempt in range(1, max_retries + 1):
            try:
                if not self.nc:
                    if attempt == max_retries:
                        raise RuntimeError("Not connected to NATS after multiple attempts")
                    self.logger.warning(f"NATS not connected on call attempt {attempt}. Trying to connect...")
                    try:
                        await self.connect()
                    except Exception as e:
                        self.logger.warning(f"Connection attempt {attempt} failed: {e}. Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                        continue
                
                response = await self.nc.request(
                    subject,
                    json.dumps(payload).encode(),
                    timeout=timeout
                )
                return json.loads(response.data.decode())
            except Exception as e:
                if attempt == max_retries:
                    self.logger.error(f"Failed to call {subject} after {max_retries} attempts: {e}")
                    raise
                self.logger.warning(f"Call attempt {attempt} failed: {e}. Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            
    async def subscribe(self, subject: str, callback: Callable, queue_group: Optional[str] = None):
        """
        Subscribe to a subject.
        
        Args:
            subject (str): Subject to subscribe to
            callback (Callable): Callback function to handle messages
            queue_group (Optional[str]): Queue group for load balancing
        """
        # Retry logic for subscribing if not connected
        max_retries = 5
        retry_delay = 3  # seconds
        
        async def wrapped_callback(msg):
            try:
                payload = json.loads(msg.data.decode())
                await callback(payload, msg.subject, msg.reply)
            except Exception as e:
                self.logger.error(f"Error in subscription callback: {e}", exc_info=True)
        
        for attempt in range(1, max_retries + 1):
            try:
                if not self.nc:
                    if attempt == max_retries:
                        raise RuntimeError("Not connected to NATS after multiple attempts")
                    self.logger.warning(f"NATS not connected on subscribe attempt {attempt}. Trying to connect...")
                    try:
                        await self.connect()
                    except Exception as e:
                        self.logger.warning(f"Connection attempt {attempt} failed: {e}. Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                        continue
                
                sub = await self.nc.subscribe(
                    subject,
                    queue=queue_group,
                    cb=wrapped_callback
                )
                self.subscriptions[subject] = sub
                self.logger.info(f"Successfully subscribed to {subject}")
                return
            except Exception as e:
                if attempt == max_retries:
                    self.logger.error(f"Failed to subscribe to {subject} after {max_retries} attempts: {e}")
                    raise
                self.logger.warning(f"Subscribe attempt {attempt} failed: {e}. Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            
    async def unsubscribe(self, subject: str):
        """
        Unsubscribe from a subject.
        
        Args:
            subject (str): Subject to unsubscribe from
        """
        if subject in self.subscriptions:
            await self.subscriptions[subject].unsubscribe()
            del self.subscriptions[subject]
            self.logger.info(f"Unsubscribed from {subject}")

class Router:
    """
    Message router for handling different message types.
    """
    
    def __init__(self, client: NatsClient):
        """
        Initialize a new Router.
        
        Args:
            client (NatsClient): NATS client
        """
        self.client = client
        self.handlers = {}
        
    def on(self, subject: str):
        """
        Decorator for registering message handlers.
        
        Args:
            subject (str): Subject to handle
            
        Returns:
            Callable: Decorator function
        """
        def decorator(func):
            self.handlers[subject] = func
            return func
        return decorator
        
    async def start(self):
        """Start the router by subscribing to all registered handlers."""
        # Try to ensure NATS is connected before subscribing
        if not self.client.nc:
            try:
                await self.client.connect()
            except Exception as e:
                self.client.logger.warning(f"Initial connection attempt in Router.start failed: {e}")
                # We'll continue anyway as subscribe has its own retry logic
        
        # Subscribe to all handlers with retry logic in the subscribe method
        for subject, handler in self.handlers.items():
            try:
                await self.client.subscribe(f"ai-radar.{subject}", handler)
            except Exception as e:
                self.client.logger.error(f"Failed to subscribe to {subject}: {e}")
                # Continue with other subjects rather than failing completely
                continue
