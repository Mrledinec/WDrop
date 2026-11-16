"""
Discovery Service Integration for Desktop App (Windows)
========================================================
Handles device discovery via UDP multicast and integrates with server API.
"""

import sys
import os
import json
import threading
from datetime import datetime
from typing import Dict, List, Optional

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from discovery_service import (
    DiscoveryService,
    PythonDiscoveryService,
    MSG_DISCOVERING,
    MSG_AVAILABLE
)
import config


class DesktopDiscoveryManager:
    """
    Manages device discovery for Windows desktop app.
    Broadcasts discovery packets and listens for responses from other devices.
    """
    
    def __init__(self):
        self.discovery_service: Optional[PythonDiscoveryService] = None
        self.is_discovering = False
        self.connected_devices: Dict[str, Dict] = {}  # sender_id -> device_info
        
        # Storage path for saved connections
        storage_path = os.path.join(project_root, "database", "connections.json")
        self.storage_path = storage_path
        
        # Load existing connections
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    saved_connections = json.load(f)
                    for conn in saved_connections:
                        self.connected_devices[conn['sender_id']] = conn
            except Exception as e:
                print(f"Error loading connections: {e}")
    
    def start_discovery(self):
        """Start broadcasting discovery packets and listening for responses"""
        
        if self.is_discovering:
            print("Discovery already running")
            return
        
        try:
            # Create service with our IP address
            # Use 0.0.0.0 to bind to all interfaces
            ip_addr = config.IP_ADDRESS or "0.0.0.0"
            
            self.discovery_service = PythonDiscoveryService(ip_address=ip_addr)
            
            # Start discovery
            self.discovery_service.start()
            self.is_discovering = True
            
            print(f"✓ Discovery started from {ip_addr}")
            self.update_status("Обнаружение устройств...")
            
        except Exception as e:
            error_msg = f"Ошибка запуска обнаружения:\n{str(e)}"
            print(error_msg)
            self.update_status("Ошибка обнаружения")
    
    def stop_discovery(self):
        """Stop discovery broadcasts"""
        
        if not self.is_discovering:
            return
        
        try:
            if self.discovery_service:
                self.discovery_service.stop()
                self.discovery_service = None
            
            self.is_discovering = False
            print("✓ Discovery stopped")
            
        except Exception as e:
            print(f"Error stopping discovery: {e}")
    
    def get_connected_devices(self) -> List[Dict]:
        """Get list of discovered devices"""
        
        with self._lock:
            return list(self.connected_devices.values())
    
    def save_connection(self, device_info: Dict):
        """Save connection to database for later reuse"""
        
        try:
            storage_path = os.path.join(project_root, "database", "connections.json")
            
            connections = []
            if os.path.exists(storage_path):
                with open(storage_path, 'r', encoding='utf-8') as f:
                    try:
                        connections = json.load(f)
                    except:
                        connections = []
            
            # Add new connection
            device_info['saved_at'] = datetime.now().isoformat()
            connections.append(device_info)
            
            # Save back to file
            with open(storage_path, 'w', encoding='utf-8') as f:
                json.dump(connections, f, ensure_ascii=False, indent=2)
                
            print(f"✓ Saved connection to {device_info['sender_id'][:8]}...")
            
        except Exception as e:
            print(f"Error saving connection: {e}")
    
    def remove_connection(self, sender_id: str):
        """Remove connection from saved list"""
        
        try:
            storage_path = os.path.join(project_root, "database", "connections.json")
            
            if not os.path.exists(storage_path):
                return False
                
            with open(storage_path, 'r', encoding='utf-8') as f:
                connections = json.load(f)
            
            # Filter out the device
            connections = [c for c in connections if c['sender_id'] != sender_id]
            
            with open(storage_path, 'w', encoding='utf-8') as f:
                json.dump(connections, f, ensure_ascii=False, indent=2)
                
            print(f"✓ Removed connection to {sender_id[:8]}...")
            return True
            
        except Exception as e:
            print(f"Error removing connection: {e}")
            return False
    
    _lock = threading.RLock()

def get_device_info(sender_id: str) -> Optional[Dict]:
    """Get saved device info by sender_id"""
    
    storage_path = os.path.join(project_root, "database", "connections.json")
    
    if not os.path.exists(storage_path):
        return None
    
    try:
        with open(storage_path, 'r', encoding='utf-8') as f:
            connections = json.load(f)
        
        for conn in connections:
            if conn['sender_id'] == sender_id:
                return conn
                
    except Exception as e:
        print(f"Error loading device info: {e}")
    
    return None


def save_device_info(sender_id: str, device_info: Dict):
    """Save device info to database"""
    
    storage_path = os.path.join(project_root, "database", "connections.json")
    
    try:
        connections = []
        if os.path.exists(storage_path):
            with open(storage_path, 'r', encoding='utf-8') as f:
                try:
                    connections = json.load(f)
                except:
                    connections = []
        
        # Add or update device
        existing_idx = None
        for i, conn in enumerate(connections):
            if conn['sender_id'] == sender_id:
                existing_idx = i
                break
        
        if existing_idx is not None:
            # Update existing connection
            connections[existing_idx] = device_info
        else:
            # Add new connection
            device_info['saved_at'] = datetime.now().isoformat()
            connections.append(device_info)
        
        # Save back to file
        with open(storage_path, 'w', encoding='utf-8') as f:
            json.dump(connections, f, ensure_ascii=False, indent=2)
            
        print(f"✓ Saved device {sender_id[:8]}...")
        
    except Exception as e:
        print(f"Error saving device info: {e}")


def remove_device_info(sender_id: str) -> bool:
    """Remove device from saved connections"""
    
    storage_path = os.path.join(project_root, "database", "connections.json")
    
    try:
        if not os.path.exists(storage_path):
            return False
            
        with open(storage_path, 'r', encoding='utf-8') as f:
            connections = json.load(f)
        
        # Filter out the device
        connections = [c for c in connections if c['sender_id'] != sender_id]
        
        with open(storage_path, 'w', encoding='utf-8') as f:
            json.dump(connections, f, ensure_ascii=False, indent=2)
            
        print(f"✓ Removed device {sender_id[:8]}...")
        return True
        
    except Exception as e:
        print(f"Error removing device: {e}")
        return False
