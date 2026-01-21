"""
Centralized Logging Configuration for Enterprise STORM

This module provides a consistent logging setup across all modules.
All modules should import and use this logger to ensure consistent formatting.

Usage:
    from src.common.logger import get_logger
    
    logger = get_logger(__name__)
    logger.info("Starting process...")

Author: Enterprise STORM Team
Created: 2026-01-21
"""

import logging
import sys
from pathlib import Path

from src.common.constants import (
    DEFAULT_LOG_LEVEL,
    LOG_FORMAT,
    LOG_DATE_FORMAT
)


def get_logger(name: str, level: str = None) -> logging.Logger:
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name (typically __name__ of the calling module)
        level: Optional log level override (default: from constants)
        
    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Only configure if logger doesn't have handlers yet
    if not logger.handlers:
        # Set level
        log_level = level or DEFAULT_LOG_LEVEL
        logger.setLevel(getattr(logging, log_level.upper()))
        
        # Create console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        
        # Create formatter
        formatter = logging.Formatter(
            fmt=LOG_FORMAT,
            datefmt=LOG_DATE_FORMAT
        )
        console_handler.setFormatter(formatter)
        
        # Add handler
        logger.addHandler(console_handler)
        
        # Prevent propagation to root logger
        logger.propagate = False
    
    return logger


def setup_logging(level: str = None) -> None:
    """
    Setup basic logging configuration for the entire application.
    This should be called once at application startup.
    
    Args:
        level: Log level (default: from constants)
    """
    log_level = level or DEFAULT_LOG_LEVEL
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT
    )
