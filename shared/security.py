"""
Security Module for AirDrop Clone Application
==============================================
Handles password authentication, timeout handling, and session management.
"""

import hashlib
import secrets
from typing import Optional, Tuple
from datetime import datetime, timedelta


class Security:
    """Security utilities for file transfer application"""
    
    @staticmethod
    def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
        """Hash a password with random salt
        
        Returns:
            Tuple of (hashed_password, salt)
        """
        if salt is None:
            salt = secrets.token_hex(16)
        
        # Use SHA-256 with salt
        hashed = hashlib.sha256(salt.encode() + password.encode()).hexdigest()
        return hashed, salt
    
    @staticmethod
    def verify_password(password: str, hashed: str, salt: str) -> bool:
        """Verify a password against stored hash"""
        return Security.hash_password(password, salt)[0] == hashed
    
    @staticmethod
    def generate_session_token() -> str:
        """Generate a secure session token"""
        # Use 32 bytes for strong security
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def verify_session_token(token: str) -> bool:
        """Verify if a session token is valid format"""
        try:
            # Check token length and format
            return len(token) == 43 and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-=' for c in token)
        except:
            return False
    
    @staticmethod
    def get_default_password() -> str:
        """Get default password (from config or hardcoded for simplicity)"""
        # Default password - can be changed in config.py
        return "admin123"  # Change this to your preferred default!
    
    @staticmethod
    def read_password_file(filepath: str) -> Optional[str]:
        """Read password from file (alternative auth method)"""
        try:
            with open(filepath, 'r') as f:
                return f.read().strip()
        except:
            return None
    
    @staticmethod
    def validate_ip_address(ip: str) -> bool:
        """Validate IPv4 address format"""
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        
        for part in parts:
            try:
                num = int(part)
                if num < 0 or num > 255:
                    return False
            except ValueError:
                return False
        
        return True
    
    @staticmethod
    def validate_port(port: int) -> bool:
        """Validate port number"""
        return 1 <= port <= 65535
    
    @staticmethod
    def is_valid_filename(filename: str) -> bool:
        """Check if filename is safe (no path traversal)"""
        # Check for path traversal attempts
        if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
            return False
        
        # Check for null bytes
        if '\x00' in filename:
            return False
        
        # Check for dangerous characters
        dangerous_chars = ['<', '>', '"', "'", '\\', '|']
        if any(char in filename for char in dangerous_chars):
            return False
        
        return True
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Remove or replace dangerous characters in filename"""
        # Remove path components
        name = filename.split('/')[-1].split('\\')[-1]
        
        # Replace dangerous characters
        safe_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-.()"
        result = ''.join(c if c in safe_chars else '_' for c in name)
        
        # Limit length
        if len(result) > 200:
            result = result[:200]
        
        return result
    
    @staticmethod
    def get_max_file_size() -> int:
        """Get maximum allowed file size (default 2GB)"""
        return 2 * 1024 * 1024 * 1024  # 2GB in bytes


# Constants
SESSION_TIMEOUT_MINUTES = 30  # Session expires after 30 minutes
PASSWORD_FILE_PATH = "password.txt"  # Alternative password storage
