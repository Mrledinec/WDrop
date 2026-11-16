"""
SQLite Storage Manager for AirDrop Clone
=========================================
Handles local storage for saved connections and transfer history.
"""

import sqlite3
import os
import contextlib
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class SavedConnection:
    """Represents a saved device connection"""
    device_id: str
    device_name: str
    ip_address: str
    port: int
    connected_at: datetime
    last_connected: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TransferHistory:
    """Represents a file transfer record"""
    source_device_id: str
    target_device_id: str
    file_path: str
    filename: str
    file_size: int
    mime_type: str
    transferred_at: datetime
    status: str  # 'completed', 'failed'
    id: Optional[int] = None


class SQLiteManager:
    """SQLite database manager for connections and transfer history"""
    
    def __init__(self, db_path: str):
        """
        Initialize SQLite manager
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._ensure_db_exists()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _ensure_db_exists(self):
        """Create database and tables if they don't exist"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Create connections table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS saved_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL UNIQUE,
                device_name TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                port INTEGER NOT NULL,
                connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_connected TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create transfer history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transfer_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_device_id TEXT NOT NULL,
                target_device_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                mime_type TEXT NOT NULL,
                transferred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'completed'
            )
        ''')
        
        conn.commit()
        conn.close()
    
    # === Connections Management ===
    
    def save_connection(self, connection: SavedConnection) -> bool:
        """
        Save or update a device connection
        
        Args:
            connection: Connection data to save
            
        Returns:
            True if successful
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Insert or replace (unique on device_id)
            cursor.execute('''
                INSERT OR REPLACE INTO saved_connections 
                (device_id, device_name, ip_address, port, connected_at, last_connected)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                connection.device_id,
                connection.device_name,
                connection.ip_address,
                connection.port,
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))
            
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False
    
    def get_connection(self, device_id: str) -> Optional[SavedConnection]:
        """Get connection by device ID"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('SELECT * FROM saved_connections WHERE device_id = ?', (device_id,))
            row = cursor.fetchone()
            
            if row:
                return SavedConnection(
                    id=row['id'],
                    device_id=row['device_id'],
                    device_name=row['device_name'],
                    ip_address=row['ip_address'],
                    port=row['port'],
                    connected_at=datetime.fromisoformat(row['connected_at']),
                    last_connected=datetime.fromisoformat(row['last_connected'])
                )
            return None
        finally:
            conn.close()
    
    def get_all_connections(self) -> List[SavedConnection]:
        """Get all saved connections, ordered by last connected (desc)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT * FROM saved_connections 
                ORDER BY last_connected DESC
            ''')
            
            rows = cursor.fetchall()
            return [
                SavedConnection(
                    id=row['id'],
                    device_id=row['device_id'],
                    device_name=row['device_name'],
                    ip_address=row['ip_address'],
                    port=row['port'],
                    connected_at=datetime.fromisoformat(row['connected_at']),
                    last_connected=datetime.fromisoformat(row['last_connected'])
                )
                for row in rows
            ]
        finally:
            conn.close()
    
    def remove_connection(self, device_id: str) -> bool:
        """Remove connection by device ID"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('DELETE FROM saved_connections WHERE device_id = ?', (device_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    # === Transfer History Management ===
    
    def add_transfer_record(self, record: TransferHistory) -> bool:
        """
        Add a transfer history record
        
        Args:
            record: Transfer history to add
            
        Returns:
            True if successful
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO transfer_history 
                (source_device_id, target_device_id, file_path, filename, file_size, mime_type, transferred_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record.source_device_id,
                record.target_device_id,
                record.file_path,
                record.filename,
                record.file_size,
                record.mime_type,
                datetime.now().isoformat(),
                record.status
            ))
            
            conn.commit()
            return True
        finally:
            conn.close()
    
    def get_transfer_history(self, device_id: Optional[str] = None) -> List[TransferHistory]:
        """
        Get transfer history
        
        Args:
            device_id: Filter by target device ID (optional)
            
        Returns:
            List of transfers, max 10 items (most recent first)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if device_id:
                cursor.execute('''
                    SELECT * FROM transfer_history 
                    WHERE target_device_id = ? 
                    ORDER BY transferred_at DESC
                    LIMIT 10
                ''', (device_id,))
            else:
                cursor.execute('''
                    SELECT * FROM transfer_history 
                    ORDER BY transferred_at DESC
                    LIMIT 10
                ''')
            
            rows = cursor.fetchall()
            return [
                TransferHistory(
                    id=row['id'],
                    source_device_id=row['source_device_id'],
                    target_device_id=row['target_device_id'],
                    file_path=row['file_path'],
                    filename=row['filename'],
                    file_size=row['file_size'],
                    mime_type=row['mime_type'],
                    transferred_at=datetime.fromisoformat(row['transferred_at']),
                    status=row['status']
                )
                for row in rows
            ]
        finally:
            conn.close()
    
    def delete_transfer_record(self, record_id: int) -> None:
        with contextlib.closing(self._get_connection()) as conn, conn:
            conn.execute("DELETE FROM transfer_history WHERE id = ?", (record_id,))

    def clear_transfer_history(self) -> None:
        with contextlib.closing(self._get_connection()) as conn, conn:
            conn.execute("DELETE FROM transfer_history")

    def get_recent_connections_count(self) -> int:
        """Get count of recent connections (last 7 days)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT COUNT(*) FROM saved_connections 
                WHERE last_connected >= datetime('now', '-7 days')
            ''')
            return cursor.fetchone()[0]
        finally:
            conn.close()


# Singleton instance for project-wide access
_db_manager: Optional[SQLiteManager] = None


def get_sqlite_manager(db_path: str) -> SQLiteManager:
    """Get or create singleton SQLite manager instance"""
    global _db_manager
    if _db_manager is None:
        _db_manager = SQLiteManager(db_path)
    return _db_manager
