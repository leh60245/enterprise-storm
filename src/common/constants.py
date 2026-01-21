"""
Centralized Constants for Enterprise STORM

This module contains all magic numbers and configuration constants
used across the application to improve maintainability.

Author: Enterprise STORM Team
Created: 2026-01-21
"""

# =============================================================================
# STORM Engine Configuration
# =============================================================================

# Maximum number of threads for parallel STORM execution
# This is a hard limit to prevent API rate limiting
STORM_MAX_THREAD_LIMIT = 5

# Default thread count for STORM runner (safe value)
STORM_DEFAULT_THREAD_COUNT = 3

# Maximum conversation turns for STORM dialogue
STORM_MAX_CONV_TURN = 3

# Maximum perspectives to generate
STORM_MAX_PERSPECTIVE = 3

# Default top-k for retrieval
STORM_DEFAULT_SEARCH_TOP_K = 10


# =============================================================================
# Retry Configuration
# =============================================================================

# Maximum retries for file operations (e.g., waiting for file creation)
FILE_OPERATION_MAX_RETRIES = 10

# Maximum retries for STORM runner execution (rate limit handling)
STORM_RUN_MAX_RETRIES = 2

# Base wait time (seconds) for rate limit retry
RATE_LIMIT_BASE_WAIT_SECONDS = 10

# Wait interval (seconds) between file check retries
FILE_CHECK_WAIT_SECONDS = 1


# =============================================================================
# Progress Reporting
# =============================================================================

# Progress percentage after PostgresRM initialization
PROGRESS_AFTER_RM_INIT = 30

# Progress percentage after engine args setup
PROGRESS_AFTER_ENGINE_SETUP = 40

# Progress percentage when STORM runner starts
PROGRESS_STORM_RUNNING = 50

# Progress percentage after STORM completion (before DB save)
PROGRESS_STORM_COMPLETED = 90

# Progress percentage after successful DB save
PROGRESS_DB_SAVED = 100


# =============================================================================
# Database Configuration
# =============================================================================

# Connection timeout for PostgreSQL (seconds)
DB_CONNECTION_TIMEOUT = 5

# Batch size for embedding generation
EMBEDDING_BATCH_SIZE = 32

# Maximum text length for embedding
EMBEDDING_MAX_LENGTH = 512


# =============================================================================
# Logging Configuration
# =============================================================================

# Default log level
DEFAULT_LOG_LEVEL = "INFO"

# Log format
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'

# Log date format
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
