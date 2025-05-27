"""
Logging Module
Standardized logging setup for agents
"""
import os
import logging
import sys
from datetime import datetime

def setup_logger(name: str, level: int = None) -> logging.Logger:
    """
    Set up a logger with standardized formatting.
    
    Args:
        name (str): Logger name
        level (int, optional): Logging level. Defaults to INFO or from environment.
        
    Returns:
        logging.Logger: Configured logger
    """
    if level is None:
        level_name = os.getenv("LOG_LEVEL", "INFO")
        level = getattr(logging, level_name)
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Clear existing handlers to avoid duplicates
    if logger.hasHandlers():
        logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # Format with timestamp, logger name, level, and message
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    
    # Add file handler if LOG_FILE is set
    log_file = os.getenv("LOG_FILE")
    if log_file:
        # Create logs directory if it doesn't exist
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger
