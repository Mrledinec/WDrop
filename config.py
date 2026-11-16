"""
Project Configuration Settings
==============================

These settings are shared across both Windows (desktop) and Android (mobile) applications.
"""

# =============================================================================
# NETWORK CONFIGURATION
# =============================================================================

# Server port for file transfers
PORT = 8000

# Host to bind (use '0.0.0.0' to accept connections from all network interfaces)
HOST = "0.0.0.0"

# =============================================================================
# FILE TRANSFER SETTINGS
# =============================================================================

# Maximum file size for transfers (in bytes)
MAX_FILE_SIZE_GB = 2.0
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_GB * 1024 * 1024 * 1024  # 2GB in bytes

# File size warning threshold (80% of max)
FILE_SIZE_WARNING_PERCENTAGE = 0.80

# Allowed file extensions (empty means all types allowed)
ALLOWED_EXTENSIONS = []  # Empty list = all file types allowed

# =============================================================================
# CONNECTION SETTINGS
# =============================================================================

# Connection timeout in seconds (idle connections will be closed after this time)
CONNECTION_TIMEOUT_SECONDS = 300  # 5 minutes

# Polling interval for HTTP polling fallback (in seconds)
POLLING_INTERVAL_SECONDS = 2.0

# WebSocket ping interval (in seconds) - keep-alive mechanism
WEBSOCKET_PING_INTERVAL = 30.0

# =============================================================================
# HISTORY SETTINGS
# =============================================================================

# Maximum number of transfers to store in history
HISTORY_MAX_ENTRIES = 10

# History storage location relative to app directory
HISTORY_DATABASE_PATH = "database/transfer_history.db"

# Device connections storage path
DEVICES_DATABASE_PATH = "database/devices.db"

# =============================================================================
# SECURITY SETTINGS
# =============================================================================

# Password file location (created on first run)
PASSWORD_FILE_PATH = "security/password.txt"

# HTTP authentication (Basic Auth with password from file)
USE_HTTP_AUTH = True

# =============================================================================
# NOTIFICATION SETTINGS
# =============================================================================

# Show Windows balloon notifications for transfers
SHOW_WINDOWS_NOTIFICATIONS = True

# Notification delay in seconds after transfer completes
NOTIFICATION_DELAY_SECONDS = 3

# =============================================================================
# UI/UX SETTINGS
# =============================================================================

# Default window size for desktop app (width, height)
WINDOW_WIDTH = 600
WINDOW_HEIGHT = 500

# App name
APP_NAME = "AirDrop Clone"

# =============================================================================
# PATHS
# =============================================================================

import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DESKTOP_DIR = os.path.join(PROJECT_ROOT, "desktop_win")
ANDROID_APP_DIR = os.path.join(PROJECT_ROOT, "android_app")
SHARED_DIR = os.path.join(PROJECT_ROOT, "shared")
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")
