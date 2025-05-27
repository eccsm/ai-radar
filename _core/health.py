#!/usr/bin/env python
"""
Health check module for AI Radar agents.
Provides a standardized health check endpoint for all agents.
"""
import asyncio
import logging
from aiohttp import web
import socket
import os
import json
from datetime import datetime, timezone

class HealthServer:
    """
    Simple HTTP server that provides health check endpoints for Kubernetes probes.
    Implements /healthz (liveness), /readyz (readiness), and /metrics (Prometheus).
    """
    
    def __init__(self, agent_name, port=8000, logger=None):
        """
        Initialize the health check server.
        
        Args:
            agent_name: Name of the agent (e.g., "fetcher", "summariser")
            port: Port to listen on (default: 8000)
            logger: Logger instance (optional)
        """
        self.agent_name = agent_name
        self.port = int(os.getenv(f"{agent_name.upper()}_HEALTH_PORT", port))
        self.logger = logger or logging.getLogger(__name__)
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
        """
        Handle liveness probe requests.
        Returns 200 if the agent is running, 503 otherwise.
        """
        if self.status in ["running", "starting"]:
            return web.Response(text="OK")
        return web.Response(status=503, text="Service Unavailable")
    
    async def handle_readiness(self, request):
        """
        Handle readiness probe requests.
        Returns 200 if the agent is ready to receive requests, 503 otherwise.
        """
        if self.status == "running":
            return web.Response(text="Ready")
        return web.Response(status=503, text="Not Ready")
    
    async def handle_metrics(self, request):
        """
        Handle Prometheus metrics requests.
        Returns metrics in Prometheus format.
        """
        hostname = socket.gethostname()
        uptime_seconds = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        
        metrics_text = []
        metrics_text.append(f"# HELP {self.agent_name}_up Agent up/down status")
        metrics_text.append(f"# TYPE {self.agent_name}_up gauge")
        metrics_text.append(f"{self.agent_name}_up{{instance=\"{hostname}\"}} {1 if self.status == 'running' else 0}")
        
        metrics_text.append(f"# HELP {self.agent_name}_uptime_seconds Time since agent started in seconds")
        metrics_text.append(f"# TYPE {self.agent_name}_uptime_seconds counter")
        metrics_text.append(f"{self.agent_name}_uptime_seconds{{instance=\"{hostname}\"}} {uptime_seconds}")
        
        metrics_text.append(f"# HELP {self.agent_name}_messages_processed Total messages processed")
        metrics_text.append(f"# TYPE {self.agent_name}_messages_processed counter")
        metrics_text.append(f"{self.agent_name}_messages_processed{{instance=\"{hostname}\"}} {self.metrics['messages_processed']}")
        
        metrics_text.append(f"# HELP {self.agent_name}_errors Total errors encountered")
        metrics_text.append(f"# TYPE {self.agent_name}_errors counter")
        metrics_text.append(f"{self.agent_name}_errors{{instance=\"{hostname}\"}} {self.metrics['errors']}")
        
        return web.Response(text="\n".join(metrics_text), content_type="text/plain")
    
    async def start(self):
        """Start the health check server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '0.0.0.0', self.port)
        await self.site.start()
        self.logger.info(f"Health check server listening on port {self.port}")
    
    async def stop(self):
        """Stop the health check server."""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        self.logger.info("Health check server stopped")
    
    def set_ready(self):
        """Mark the agent as ready to receive requests."""
        self.status = "running"
        self.logger.info(f"Agent {self.agent_name} marked as ready")
    
    def set_not_ready(self):
        """Mark the agent as not ready to receive requests."""
        self.status = "not_ready"
        self.logger.info(f"Agent {self.agent_name} marked as not ready")
    
    def increment_messages(self):
        """Increment the messages processed counter."""
        self.metrics["messages_processed"] += 1
        self.metrics["last_message_time"] = datetime.now(timezone.utc).isoformat()
    
    def increment_errors(self):
        """Increment the errors counter."""
        self.metrics["errors"] += 1
