"""
Database Module
Helper functions for PostgreSQL database access
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional
import asyncpg

class PostgresClient:
    """
    Client for PostgreSQL database.
    Provides a simple interface for database operations.
    """
    
    def __init__(self, connection_string: str, logger: logging.Logger, min_size=2, max_size=10):
        """
        Initialize a new PostgreSQL client.
        
        Args:
            connection_string (str): Database connection string
            logger (logging.Logger): Logger instance
            min_size (int): Minimum number of connections in the pool
            max_size (int): Maximum number of connections in the pool
        """
        self.connection_string = connection_string
        self.logger = logger
        self.pool = None
        self.min_size = min_size
        self.max_size = max_size
        
    async def connect(self):
        """Connect to the database."""
        try:
            # Enhanced logging with connection string (masking password)
            connection_parts = self.connection_string.split('@')
            if len(connection_parts) > 1:
                auth_part = connection_parts[0].split(':')  
                masked_auth = f"{auth_part[0]}:****"
                masked_conn_string = f"{masked_auth}@{connection_parts[1]}"
            else:
                masked_conn_string = "[connection string format error]"
                
            self.logger.info(f"Connecting to PostgreSQL with: {masked_conn_string}")
            
            # Try to parse and validate connection string
            try:
                conn_parts = self.connection_string.split('://')
                if len(conn_parts) != 2 or not conn_parts[1]:
                    self.logger.error(f"Invalid connection string format: missing scheme or details")
            except Exception as parse_err:
                self.logger.error(f"Error parsing connection string: {parse_err}")
            
            # Attempt to create the pool with more detailed error info and size limits
            self.pool = await asyncpg.create_pool(
                self.connection_string,
                min_size=self.min_size,
                max_size=self.max_size,
                timeout=10.0,
                command_timeout=30.0
            )
            self.logger.info(f"Successfully connected to PostgreSQL with pool size: min={self.min_size}, max={self.max_size}")
            
            # Verify the connection by executing a test query
            async with self.pool.acquire() as conn:
                version = await conn.fetchval("SELECT version()")
                self.logger.info(f"PostgreSQL version: {version}")
                
        except asyncpg.exceptions.InvalidPasswordError:
            self.logger.error("Failed to connect: Invalid password for PostgreSQL user")
            raise
        except asyncpg.exceptions.InvalidCatalogNameError:
            self.logger.error("Failed to connect: Database does not exist")
            raise
        except asyncpg.exceptions.CannotConnectNowError:
            self.logger.error("Failed to connect: Server is not accepting connections")
            raise
        except asyncpg.exceptions.TooManyConnectionsError as tmce:
            self.logger.error(f"Too many PostgreSQL connections: {tmce}", exc_info=True)
            # Consider reducing pool size or waiting before retry
            raise
        except asyncpg.exceptions.PostgresConnectionError as pg_err:
            self.logger.error(f"PostgreSQL connection error: {pg_err}", exc_info=True)
            raise
        except Exception as e:
            self.logger.error(f"Failed to connect to PostgreSQL: {e}", exc_info=True)
            raise
            
    async def close(self):
        """Close database connection."""
        if self.pool:
            await self.pool.close()
            self.logger.info("PostgreSQL connection closed")
            
    async def execute(self, query: str, *args, **kwargs):
        """
        Execute a query.
        
        Args:
            query (str): SQL query
            *args: Query parameters
            **kwargs: Additional parameters
            
        Returns:
            str: Query result
        """
        if not self.pool:
            raise RuntimeError("Not connected to PostgreSQL")
            
        try:
            async with self.pool.acquire() as conn:
                return await conn.execute(query, *args, **kwargs)
        except asyncpg.exceptions.TooManyConnectionsError as tmce:
            self.logger.error(f"Too many connections during execute: {tmce}", exc_info=True)
            # Wait briefly before allowing caller to retry
            await asyncio.sleep(1)
            raise
        except Exception as e:
            self.logger.error(f"Failed to execute query: {e}", exc_info=True)
            raise
            
    async def fetch(self, query: str, *args, **kwargs) -> List[Dict[str, Any]]:
        """
        Fetch multiple rows.
        
        Args:
            query (str): SQL query
            *args: Query parameters
            **kwargs: Additional parameters
            
        Returns:
            List[Dict[str, Any]]: Query results
        """
        if not self.pool:
            raise RuntimeError("Not connected to PostgreSQL")
            
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetch(query, *args, **kwargs)
        except asyncpg.exceptions.TooManyConnectionsError as tmce:
            self.logger.error(f"Too many connections during fetch: {tmce}", exc_info=True)
            # Wait briefly before allowing caller to retry
            await asyncio.sleep(1)
            raise
        except Exception as e:
            self.logger.error(f"Failed to fetch rows: {e}", exc_info=True)
            raise
            
    async def fetchrow(self, query: str, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Fetch a single row.
        
        Args:
            query (str): SQL query
            *args: Query parameters
            **kwargs: Additional parameters
            
        Returns:
            Optional[Dict[str, Any]]: Query result
        """
        if not self.pool:
            raise RuntimeError("Not connected to PostgreSQL")
            
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchrow(query, *args, **kwargs)
        except asyncpg.exceptions.TooManyConnectionsError as tmce:
            self.logger.error(f"Too many connections during fetchrow: {tmce}", exc_info=True)
            # Wait briefly before allowing caller to retry
            await asyncio.sleep(1)
            raise
        except Exception as e:
            self.logger.error(f"Failed to fetch row: {e}", exc_info=True)
            raise
            
    async def fetchval(self, query: str, *args, **kwargs) -> Any:
        """
        Fetch a single value.
        
        Args:
            query (str): SQL query
            *args: Query parameters
            **kwargs: Additional parameters
            
        Returns:
            Any: Query result
        """
        if not self.pool:
            raise RuntimeError("Not connected to PostgreSQL")
            
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchval(query, *args, **kwargs)
        except asyncpg.exceptions.TooManyConnectionsError as tmce:
            self.logger.error(f"Too many connections during fetchval: {tmce}", exc_info=True)
            # Wait briefly before allowing caller to retry
            await asyncio.sleep(1)
            raise
        except Exception as e:
            self.logger.error(f"Failed to fetch value: {e}", exc_info=True)
            raise
            
    async def transaction(self):
        """
        Create a transaction.
        
        Returns:
            asyncpg.Transaction: Transaction object
        """
        if not self.pool:
            raise RuntimeError("Not connected to PostgreSQL")
            
        conn = await self.pool.acquire()
        return conn.transaction()
