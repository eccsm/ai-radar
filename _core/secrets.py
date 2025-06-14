#!/usr/bin/env python
"""
Secrets management module for AI Radar agents.
Provides a unified interface for accessing secrets from various sources:
1. Environment variables
2. Docker Compose secrets (files in /run/secrets/)
3. HashiCorp Vault (when available)
"""
import os
import logging
import json
from pathlib import Path
import asyncio
from typing import Dict, Optional, Any, List

# Optional Vault support - don't fail if hvac is not installed
try:
    import hvac
    import requests
    VAULT_AVAILABLE = True
except ImportError:
    VAULT_AVAILABLE = False

class SecretsManager:
    """
    Unified secrets manager that retrieves secrets from multiple sources
    with a consistent fallback strategy.
    """
    
    def __init__(self, logger=None):
        """
        Initialize the secrets manager.
        
        Args:
            logger: Logger instance (optional)
        """
        self.logger = logger or logging.getLogger(__name__)
        self.vault_client = None
        self.secrets_cache: Dict[str, str] = {}
        self.vault_token_path = os.getenv("VAULT_TOKEN_PATH", "/vault/token")
        self.vault_url = os.getenv("VAULT_ADDR", "http://vault:8200")
        self.vault_mount = os.getenv("VAULT_MOUNT", "ai-radar")
        self.vault_role = os.getenv("VAULT_ROLE", "ai-radar")
        
        # Docker Compose secrets directory
        self.secrets_dir = Path("/run/secrets")
        
        # Try to initialize Vault client if available
        if VAULT_AVAILABLE:
            self._init_vault()
    
    def _init_vault(self) -> None:
        """Initialize the Vault client if possible."""
        try:
            # Check if we have a token file (from Vault Agent)
            if Path(self.vault_token_path).exists():
                with open(self.vault_token_path, "r") as f:
                    token = f.read().strip()
                self.vault_client = hvac.Client(url=self.vault_url, token=token)
                self.logger.info(f"Initialized Vault client with token from {self.vault_token_path}")
            else:
                # Try to use environment variable
                token = os.getenv("VAULT_TOKEN")
                if token:
                    self.vault_client = hvac.Client(url=self.vault_url, token=token)
                    self.logger.info("Initialized Vault client with token from environment")
                else:
                    # Try to use the default root token for development
                    self.vault_client = hvac.Client(url=self.vault_url, token="root")
                    try:
                        if self.vault_client.is_authenticated():
                            self.logger.info("Initialized Vault client with default root token")
                        else:
                            self.logger.warning("Default root token authentication failed")
                            self.vault_client = None
                    except Exception:
                        self.logger.warning("No Vault token available, Vault secrets will not be accessible")
                        self.vault_client = None
        except Exception as e:
            self.logger.warning(f"Failed to initialize Vault client: {e}")
            self.vault_client = None
    
    def _read_compose_secret(self, secret_name: str) -> Optional[str]:
        """
        Read a secret from Docker Compose secrets directory.
        
        Args:
            secret_name: Name of the secret
            
        Returns:
            Secret value or None if not found
        """
        secret_path = self.secrets_dir / secret_name
        if secret_path.exists():
            try:
                with open(secret_path, "rb") as f:
                    content_bytes = f.read()
                return content_bytes.decode('utf-8-sig').strip()
            except Exception as e:
                self.logger.warning(f"Failed to read Docker Compose secret {secret_name}: {e}")
        return None
    
    def _read_vault_secret(self, secret_path: str, key: str) -> Optional[str]:
        """
        Read a secret from Vault.
        
        Args:
            secret_path: Path to the secret in Vault
            key: Key within the secret
            
        Returns:
            Secret value or None if not found
        """
        if not self.vault_client:
            return None
        
        try:
            # Make sure the path doesn't have leading/trailing slashes
            secret_path = secret_path.strip("/")
            
            # Read the secret from Vault
            response = self.vault_client.secrets.kv.v2.read_secret_version(
                path=secret_path,
                mount_point=self.vault_mount
            )
            
            # Extract the value for the specified key
            if response and "data" in response and "data" in response["data"]:
                return response["data"]["data"].get(key)
        except Exception as e:
            self.logger.debug(f"Failed to read Vault secret {secret_path}/{key}: {e}")
            
            # Try direct HTTP request as fallback
            try:
                headers = {"X-Vault-Token": self.vault_client.token}
                url = f"{self.vault_url}/v1/{self.vault_mount}/data/{secret_path}"
                response = requests.get(url, headers=headers, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if "data" in data and "data" in data["data"]:
                        return data["data"]["data"].get(key)
            except Exception as e2:
                self.logger.warning(f"Failed to read Vault secret via HTTP: {e2}")
        
        return None
    
    def get_secret(self, name: str, default: Optional[str] = None) -> str:
        """
        Get a secret value using the following fallback strategy:
        1. Check cache
        2. Try Vault secret (prioritized)
        3. Check environment variable
        4. Check Docker Compose secret
        5. Return default value
        
        Args:
            name: Name of the secret (e.g., "POSTGRES_PASSWORD")
            default: Default value if secret is not found
            
        Returns:
            Secret value or default
        """
        # Check cache first
        if name in self.secrets_cache:
            return self.secrets_cache[name]
            
        # Temporarily skip Vault for MinIO endpoint to force environment variable usage
        if name != "MINIO_ENDPOINT":
            # Try Vault secret first (prioritized)
            # Map common secret patterns to Vault paths
            vault_value = None
            
            # Special case handling for common secret patterns
            if name.startswith("POSTGRES_") or name.startswith("DB_"):
                # Database secrets
                key = name.replace("POSTGRES_", "").replace("DB_", "").lower()
                vault_value = self._read_vault_secret("database", key)
            elif name.startswith("NATS_"):
                # NATS secrets
                key = name.replace("NATS_", "").lower()
                vault_value = self._read_vault_secret("nats", key)
            elif name.startswith("MINIO_"):
                # MinIO secrets
                key = name.replace("MINIO_", "").lower()
                vault_value = self._read_vault_secret("minio", key)
            elif name.endswith("_KEY") or name.endswith("_API_KEY") or name.endswith("_TOKEN"):
                # API keys and tokens
                key = name.lower().replace("_api_key", "").replace("_key", "").replace("_token", "")
                vault_value = self._read_vault_secret("api-keys", key)
            elif "_" in name:
                # Generic pattern: SERVICE_KEY -> service/key
                parts = name.lower().split("_")
                if len(parts) >= 2:
                    path = parts[0]
                    key = "_".join(parts[1:])
                    vault_value = self._read_vault_secret(path, key)
            
            if vault_value is not None:
                self.secrets_cache[name] = vault_value
                return vault_value
        
        # Try environment variable
        value = os.getenv(name)
        if value is not None:
            self.secrets_cache[name] = value
            return value
        
        # Try environment variable with _FILE suffix
        file_env = os.getenv(f"{name}_FILE")
        if file_env and Path(file_env).exists():
            try:
                with open(file_env, "rb") as f:
                    content_bytes = f.read()
                value = content_bytes.decode('utf-8-sig').strip()
                self.secrets_cache[name] = value
                return value
            except Exception as e:
                self.logger.warning(f"Failed to read secret from file {file_env}: {e}")
        
        # Try Docker Compose secret
        value = self._read_compose_secret(name.lower())
        if value is not None:
            self.secrets_cache[name] = value
            return value
        
        # Return default value
        return default
    
    def get_database_url(self) -> str:
        """
        Construct a database URL using individual secrets.
        First tries to get a complete URL from Vault, then falls back to individual components.
        
        Returns:
            Database URL string
        """
        # Try to get complete URL from Vault first
        if self.vault_client:
            try:
                # Try to read the complete URL from Vault
                url = self._read_vault_secret("database", "url")
                if url:
                    return url
            except Exception as e:
                self.logger.debug(f"Failed to read database URL from Vault: {e}")
        
        # Fall back to individual components
        host = self.get_secret("POSTGRES_HOST", "db")
        port = self.get_secret("POSTGRES_PORT", "5432")
        user = self.get_secret("POSTGRES_USER", "ai")
        password = self.get_secret("POSTGRES_PASSWORD", "ai_pwd")
        db = self.get_secret("POSTGRES_DB", "ai_radar")
        
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"
    
    def get_nats_url(self) -> str:
        """
        Construct a NATS URL using individual secrets.
        
        Returns:
            NATS URL string
        """
        host = self.get_secret("NATS_HOST", "nats")
        port = self.get_secret("NATS_PORT", "4222")
        
        return f"nats://{host}:{port}"
    
    def get_minio_config(self) -> Dict[str, str]:
        """
        Get MinIO configuration.
        
        Returns:
            Dictionary with MinIO configuration
        """
        return {
            "endpoint": self.get_secret("MINIO_ENDPOINT", "http://minio:9000"),
            "access_key": self.get_secret("AWS_ACCESS_KEY_ID", "minio"),
            "secret_key": self.get_secret("AWS_SECRET_ACCESS_KEY", "minio_pwd"),
            "bucket": self.get_secret("BUCKET_NAME", "ai-radar-content")
        }
    
    def get_openai_api_key(self) -> str:
        """
        Get OpenAI API key.
        
        Returns:
            OpenAI API key
        """
        return self.get_secret("OPENAI_API_KEY", "")
    
    def get_newsapi_key(self) -> str:
        """
        Get NewsAPI key.
        
        Returns:
            NewsAPI key
        """
        return self.get_secret("NEWSAPI_KEY", "")

    def get_linkedin_config(self) -> Dict[str, str]:
        """
        Get LinkedIn configuration for sharing.
        
        Returns:
            Dictionary with LinkedIn configuration
        """
        return {
            "access_token": self.get_secret("LINKEDIN_ACCESS_TOKEN", ""),
            "author_urn": self.get_secret("LINKEDIN_AUTHOR_URN", "")
        }
