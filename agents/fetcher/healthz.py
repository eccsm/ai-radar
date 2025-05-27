#!/usr/bin/env python
"""
Health check endpoint for the fetcher agent.
Provides HTTP endpoints for Kubernetes liveness and readiness probes.
"""
import asyncio
import logging
import os
from aiohttp import web
import socket
import json
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class HealthServer:
    """Simple HTTP server for health check endpoints."""
    
    def __init__(self, port=8000):
        """Initialize the health check server."""
        self.port = int(os.getenv("HEALTH_PORT", port))
        self.app = web.Application()
        self.start_time = datetime.now(timezone.utc)
        self.status = "starting"
        self.metrics = {
            "messages_processed": 0,
            "errors": 0,
            "last_message_time": None
        }
        
        # Setup routes
        self.app.add_routes([
            web.get('/healthz', self.handle_liveness),
            web.get('/readyz', self.handle_readiness),
            web.get('/metrics', self.handle_metrics)
        ])
        
        self.runner = None
        self.site = None
    
    async def handle_liveness(self, request):
        """Handle liveness probe requests."""
        if self.status in ["running", "starting"]:
            return web.Response(text="OK")
        return web.Response(status=503, text="Service Unavailable")
    
    async def handle_readiness(self, request):
        """Handle readiness probe requests."""
        if self.status == "running":
            return web.Response(text="Ready")
        return web.Response(status=503, text="Not Ready")
    
    async def handle_metrics(self, request):
        """Handle Prometheus metrics requests."""
        hostname = socket.gethostname()
        uptime_seconds = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        
        metrics_text = []
        metrics_text.append(f"# HELP fetcher_up Agent up/down status")
        metrics_text.append(f"# TYPE fetcher_up gauge")
        metrics_text.append(f"fetcher_up{{instance=\"{hostname}\"}} {1 if self.status == 'running' else 0}")
        
        metrics_text.append(f"# HELP fetcher_uptime_seconds Time since agent started in seconds")
        metrics_text.append(f"# TYPE fetcher_uptime_seconds counter")
        metrics_text.append(f"fetcher_uptime_seconds{{instance=\"{hostname}\"}} {uptime_seconds}")
        
        metrics_text.append(f"# HELP fetcher_messages_processed Total messages processed")
        metrics_text.append(f"# TYPE fetcher_messages_processed counter")
        metrics_text.append(f"fetcher_messages_processed{{instance=\"{hostname}\"}} {self.metrics['messages_processed']}")
        
        metrics_text.append(f"# HELP fetcher_errors Total errors encountered")
        metrics_text.append(f"# TYPE fetcher_errors counter")
        metrics_text.append(f"fetcher_errors{{instance=\"{hostname}\"}} {self.metrics['errors']}")
        
        return web.Response(text="\n".join(metrics_text), content_type="text/plain")
    
    async def start(self):
        """Start the health check server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '0.0.0.0', self.port)
        await self.site.start()
        logger.info(f"Health check server listening on port {self.port}")
    
    async def stop(self):
        """Stop the health check server."""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        logger.info("Health check server stopped")
    
    def set_ready(self):
        """Mark the agent as ready to receive requests."""
        self.status = "running"
        logger.info("Agent marked as ready")
    
    def set_not_ready(self):
        """Mark the agent as not ready to receive requests."""
        self.status = "not_ready"
        logger.info("Agent marked as not ready")
    
    def increment_messages(self):
        """Increment the messages processed counter."""
        self.metrics["messages_processed"] += 1
        self.metrics["last_message_time"] = datetime.now(timezone.utc).isoformat()
    
    def increment_errors(self):
        """Increment the errors counter."""
        self.metrics["errors"] += 1

async def run_health_server():
    """Run the health check server as a standalone process."""
    logging.basicConfig(level=logging.INFO)
    server = HealthServer()
    await server.start()
    server.set_ready()
    
    try:
        while True:
            await asyncio.sleep(3600)  # Keep running
    finally:
        await server.stop()

if __name__ == "__main__":
    asyncio.run(run_health_server())
