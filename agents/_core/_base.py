"""
BaseAgent Implementation
Core functionality for all AI Radar agents

Enhanced with health checks, secrets management, and Kubernetes readiness.
"""
import os
import logging
import asyncio
import sys
import socket
from typing import Dict, Any, Optional, List

# Add project root to path to import _core modules
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

# Import core modules from project root rather than local directory
import sys as _sys
_original_path = list(_sys.path)
_sys.path = [p for p in _sys.path if 'agents/_core' not in p.replace('\\', '/')]

# Now import from root _core
from _core.health import HealthServer
from _core.secrets import SecretsManager

# Restore the path
_sys.path = _original_path

from ._rpc import NatsClient
from ._db import PostgresClient
from ._logging import setup_logger

class BaseAgent:
    """
    Base Agent class that provides common functionality for all agents.
    
    Attributes:
        name (str): Name of the agent
        bus (NatsClient): NATS client for messaging
        db (PostgresClient): Database client
        logger (logging.Logger): Logger instance
        health (HealthServer): Health check server
        secrets (SecretsManager): Secrets manager
    """
    
    def __init__(self, name: str):
        """
        Initialize a new BaseAgent.
        
        Args:
            name (str): Name of the agent
        """
        self.name = name
        self.logger = setup_logger(name)
        
        # Initialize secrets manager
        self.secrets = SecretsManager(self.logger)
        
        # Get service URLs from secrets manager
        nats_url = self.secrets.get_nats_url()
        postgres_url = self.secrets.get_database_url()
        
        # Initialize clients
        self.bus = NatsClient(nats_url, self.logger)
        self.db = PostgresClient(postgres_url, self.logger)
        
        # Initialize health check server
        health_port = int(os.getenv(f"{name.upper()}_HEALTH_PORT", 8000))
        self.health = HealthServer(name, health_port, self.logger)
        
        # Track readiness state
        self.is_ready = False
        
        # Get hostname for metrics and logging
        self.hostname = socket.gethostname()
        
    async def setup(self):
        """Set up connections and resources."""
        self.logger.info(f"Setting up {self.name} agent on {self.hostname}")
        
        # Start health check server first so it can report status during setup
        try:
            await self.health.start()
        except Exception as e:
            self.logger.error(f"Failed to start health check server: {e}", exc_info=True)
            # Continue anyway - health checks are important but not critical
        
        # Add retry logic for NATS connection
        max_retries = 5
        retry_delay = 5  # seconds
        
        for attempt in range(1, max_retries + 1):
            try:
                self.logger.info(f"Connecting to NATS at {self.bus.url} (attempt {attempt}/{max_retries})")
                await self.bus.connect()
                self.logger.info("Successfully connected to NATS")
                break
            except Exception as e:
                if attempt == max_retries:
                    self.logger.error(f"Failed to connect to NATS after {max_retries} attempts: {e}")
                    self.health.metrics["errors"] += 1
                    raise
                self.logger.warning(f"NATS connection attempt {attempt} failed: {e}. Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
        
        # Connect to database
        try:
            self.logger.info(f"Connecting to database at {self.db.url.split('@')[1] if '@' in self.db.url else self.db.url}")
            await self.db.connect()
            self.logger.info("Successfully connected to database")
        except Exception as e:
            self.logger.error(f"Failed to connect to database: {e}", exc_info=True)
            self.health.metrics["errors"] += 1
            raise
            
        # Setup complete - mark as ready for health checks
        self.is_ready = True
        self.health.set_ready()
        self.logger.info(f"{self.name} agent setup complete and ready for requests")
        
    async def teardown(self):
        """Clean up connections and resources."""
        self.logger.info(f"Tearing down {self.name} agent")
        
        # Mark as not ready for health checks
        self.is_ready = False
        self.health.set_not_ready()
        
        # Close connections
        try:
            await self.bus.close()
            self.logger.info("NATS connection closed")
        except Exception as e:
            self.logger.error(f"Error closing NATS connection: {e}", exc_info=True)
            
        try:
            await self.db.close()
            self.logger.info("Database connection closed")
        except Exception as e:
            self.logger.error(f"Error closing database connection: {e}", exc_info=True)
            
        # Stop health check server
        try:
            await self.health.stop()
            self.logger.info("Health check server stopped")
        except Exception as e:
            self.logger.error(f"Error stopping health check server: {e}", exc_info=True)
            
        self.logger.info(f"{self.name} agent teardown complete")
        
    async def run(self):
        """
        Main execution loop for the agent.
        This should be overridden by subclasses.
        """
        try:
            await self.setup()
            self.logger.info(f"{self.name} agent running on {self.hostname}")
            
            # Keep the agent running until interrupted
            while True:
                # Perform any periodic health checks or maintenance here
                await asyncio.sleep(60)
                
        except asyncio.CancelledError:
            self.logger.info(f"{self.name} agent received cancellation")
        except Exception as e:
            self.logger.error(f"Error in {self.name} agent: {e}", exc_info=True)
            self.health.metrics["errors"] += 1
            self.health.set_not_ready()
        finally:
            await self.teardown()
            
    async def increment_message_count(self):
        """
        Increment the message count metric.
        This should be called by handler methods when processing messages.
        """
        self.health.increment_messages()
        
    async def increment_error_count(self):
        """
        Increment the error count metric.
        This should be called when errors occur during message processing.
        """
        self.health.increment_errors()
