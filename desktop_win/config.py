"""
Configuration for AirDrop Clone Desktop App
============================================
Centralized configuration settings for Windows desktop application.
"""

import os

# Application paths
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
storage_dir = os.path.join(project_root, "desktop_win", "storage")


# Server configuration
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8000


# Discovery service configuration
DISCOVERY_INTERVAL = 1  # Seconds between discovery scans
DISCOVERY_TIMEOUT = 3  # Timeout in seconds for connection attempts


# Maximum file size limits (bytes)
MAX_FILE_SIZE_DEFAULT = 2 * 1024 * 1024 * 1024  # 2GB default limit
MAX_FILE_SIZE_SMALL = 100 * 1024 * 1024  # 100MB for small files
MAX_FILE_SIZE_MEDIUM = 500 * 1024 * 1024  # 500MB for medium files


# Transfer history settings
MAX_HISTORY_ITEMS = 10  # Maximum transfer history items to keep


# Security settings (basic)
SECRET_KEY = "airdrop-clone-localnet-secret-key-change-in-production"


# Database path
DATABASE_PATH = os.path.join(storage_dir, "connections.db")