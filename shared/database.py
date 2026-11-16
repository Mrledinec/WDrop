"""
Database Module for AirDrop Clone Application
==============================================
Handles SQLite databases for transfer history and device connections.

Both desktop and Android applications use this shared database logic.
"""

import sqlite3
import os
from typing import List, Dict, Any, Optional
from datetime import datetime


class Database:
    """Abstract database interface (SQLite implementation below)"""
    
    @staticmethod
    def init_database(db_path: str):
        """Initialize the database and create tables if not exist"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create transfer history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transfer_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT NOT NULL,
                file_size_bytes INTEGER NOT NULL,
                status TEXT NOT NULL,
                upload_date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create devices table for saved connections
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT UNIQUE NOT NULL,
                port INTEGER NOT NULL,
                device_name TEXT,
                last_connected TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                connection_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    @staticmethod
    def add_transfer(file_name: str, file_size_bytes: int, status: str):
        """Add a transfer to history (keeps only last 10)"""
        db_path = "database/transfer_history.db"
        
        # Initialize if not exists
        if not os.path.exists(db_path):
            Database.init_database(db_path)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Insert new record
        upload_date = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO transfer_history (file_name, file_size_bytes, status, upload_date)
            VALUES (?, ?, ?, ?)
        ''', (file_name, file_size_bytes, status, upload_date))
        
        # Delete old records to keep only 10 entries
        cursor.execute('DELETE FROM transfer_history WHERE id <= ?', (cursor.lastrowid + 1 - 10,))
        
        conn.commit()
        conn.close()
    
    @staticmethod
    def get_transfer_history(limit: int = 10) -> List[Dict[str, Any]]:
        """Get last N transfer records"""
        db_path = "database/transfer_history.db"
        
        if not os.path.exists(db_path):
            return []
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, file_name, file_size_bytes, status, upload_date
            FROM transfer_history
            ORDER BY created_at DESC
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                'id': row[0],
                'file_name': row[1],
                'file_size_bytes': row[2],
                'status': row[3],
                'upload_date': row[4]
            }
            for row in rows
        ]
    
    @staticmethod
    def add_device(ip_address: str, port: int, device_name: Optional[str] = None):
        """Add or update a device connection record"""
        db_path = "database/devices.db"
        
        # Initialize if not exists
        if not os.path.exists(db_path):
            Database.init_database(db_path)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get current count for this IP
        cursor.execute('SELECT connection_count FROM devices WHERE ip_address = ?', (ip_address,))
        row = cursor.fetchone()
        current_count = row[0] + 1 if row else 1
        
        # Insert or update device
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT OR REPLACE INTO devices (ip_address, port, device_name, last_connected, connection_count)
            VALUES (?, ?, ?, ?, ?)
        ''', (ip_address, port, device_name, now, current_count))
        
        conn.commit()
        conn.close()
    
    @staticmethod
    def get_saved_devices() -> List[Dict[str, Any]]:
        """Get list of all saved devices"""
        db_path = "database/devices.db"
        
        if not os.path.exists(db_path):
            return []
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, ip_address, port, device_name, last_connected, connection_count
            FROM devices
            ORDER BY last_connected DESC
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                'id': row[0],
                'ip_address': row[1],
                'port': row[2],
                'device_name': row[3],
                'last_connected': row[4],
                'connection_count': row[5]
            }
            for row in rows
        ]
    
    @staticmethod
    def get_device_by_ip(ip_address: str, port: int) -> Optional[Dict[str, Any]]:
        """Get device by IP and port"""
        db_path = "database/devices.db"
        
        if not os.path.exists(db_path):
            return None
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, ip_address, port, device_name, last_connected, connection_count
            FROM devices
            WHERE ip_address = ? AND port = ?
        ''', (ip_address, port))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'id': row[0],
                'ip_address': row[1],
                'port': row[2],
                'device_name': row[3],
                'last_connected': row[4],
                'connection_count': row[5]
            }
        return None
    
    @staticmethod
    def update_device_last_connected(ip_address: str, port: int):
        """Update last connected timestamp for a device"""
        db_path = "database/devices.db"
        
        if not os.path.exists(db_path):
            return
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        cursor.execute('''
            UPDATE devices 
            SET last_connected = ?
            WHERE ip_address = ? AND port = ?
        ''', (now, ip_address, port))
        
        conn.commit()
        conn.close()


def get_db_path(type: str) -> str:
    """Get the correct path for database files based on platform"""
    
    import os
    
    # For desktop app - relative to project root
    if type == "history":
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "database/transfer_history.db")
    elif type == "devices":
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "database/devices.db")
    
    # For Android app - in application files directory
    elif type == "history" and "android" in str(os.getcwd()).lower():
        return "/data/data/com.airdrop/files/db/transfer_history.db"
    elif type == "devices" and "android" in str(os.getcwd()).lower():
        return "/data/data/com.airdrop/files/db/devices.db"
    
    return "database/transfer_history.db"


# Initialize databases on module import
def initialize_databases():
    """Initialize all databases"""
    db_path = get_db_path("history")
    Database.init_database(db_path)
    Database.init_database(get_db_path("devices"))
