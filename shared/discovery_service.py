"""
Universal Device Discovery Service (UDP Multicast)
===================================================
Works across platforms (Windows desktop + Android app) to discover devices on local network.

Usage:
    Python: from discovery_service import DiscoveryService
    
    service = DiscoveryService()
    devices = service.get_discovered_devices()  # Get list of discovered devices
    
    android: uses platform-specific implementation via binding
"""

import json
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from abc import ABC, abstractmethod
import socket
import uuid


# =============================================================================
# DISCOVERY PROTOCOL
# =============================================================================

DISCOVERY_GROUP_IP = "224.0.0.1"  # Multicast group address (link-local)
DISCOVERY_PORT = 5678             # Discovery port
DISCOVERY_INTERVAL_SECONDS = 5    # How often to broadcast discovery packets
DISCOVERY_TTL = 2                 # Time-to-live for multicast packets

# Message types
MSG_DISCOVERING = "discovering"      # "I'm looking for devices"
MSG_AVAILABLE = "available"          # "I found you!"
MSG_HEARTBEAT = "heartbeat"         # Keep-alive ping


# =============================================================================
# DISCOVERY PACKET STRUCTURE
# =============================================================================

class DiscoveryPacket:
    """Structure of a discovery broadcast packet"""
    
    def __init__(self, sender_id: str, msg_type: str):
        self.sender_id = sender_id  # UUID of the device
        self.msg_type = msg_type
        self.timestamp = datetime.now().isoformat()
        self.os_platform = "unknown"
        self.app_name = "AirDrop Clone"
        
    def to_bytes(self) -> bytes:
        """Convert packet to bytes for network transmission"""
        # Simple format: len(sender_id)(1) + type(2) + json rest
        data = json.dumps({
            'sender_id': self.sender_id,
            'msg_type': self.msg_type,
            'timestamp': self.timestamp,
            'os_platform': self.os_platform,
            'app_name': self.app_name
        })
        return (str(len(data)).zfill(3).encode() + b'|' + 
                data.encode())
    
    @classmethod
    def from_bytes(cls, data: bytes):
        """Parse bytes back into packet"""
        try:
            prefix_len = int(data[:3])
            json_part = data[4:].decode('utf-8')
            return json.loads(json_part)
        except:
            return None


# =============================================================================
# UNIVERSAL DISCOVERY SERVICE (Python/Desktop)
# =============================================================================

class DiscoveryService(ABC):
    """Abstract base class for platform-specific discovery implementations"""
    
    @abstractmethod
    def start_discovery(self):
        """Start broadcasting discovery packets"""
        pass
    
    @abstractmethod
    def stop_discovery(self):
        """Stop broadcasting and listening"""
        pass
    
    @abstractmethod
    def get_discovered_devices(self) -> List[Dict]:
        """Get list of discovered devices"""
        pass


class PythonDiscoveryService(DiscoveryService):
    """
    Python/PyQt6 implementation for Windows desktop app.
    Uses UDP multicast to broadcast and listen for discovery packets.
    """
    
    def __init__(self, ip_address: Optional[str] = None, port: int = DISCOVERY_PORT):
        self.ip_address = ip_address or "0.0.0.0"
        self.port = port
        self.sender_id = str(uuid.uuid4())
        
        self.socket: socket.socket = None
        self.is_running = False
        
        self.discovered_devices: Dict[str, Dict] = {}  # sender_id -> device_info
        self.lock = threading.RLock()
        
    def start(self):
        """Start broadcasting discovery packets"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Enable multicast
            multicast_addr = (DISCOVERY_GROUP_IP, self.port)
            self.socket.join_group(multicast_addr[0], interface=multicast_addr[0])
            self.socket.setsockopt(socket.IPPROTO_IPMULTICAST, 
                                   socket.IP_MULTICAST_TTL, DISCOVERY_TTL)
            
            # Start broadcasting thread
            broadcast_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
            broadcast_thread.start()
            
            # Start listening thread
            listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
            listen_thread.start()
            
            self.is_running = True
            print(f"✓ Discovery service started. Sending packets from {self.sender_id}")
            
        except Exception as e:
            print(f"✗ Discovery service error: {e}")
            self.is_running = False
    
    def stop(self):
        """Stop discovery service"""
        self.is_running = False
        
        if self.socket:
            try:
                self.socket.leave_group(DISCOVERY_GROUP_IP, interface=self.ip_address)
                self.socket.close()
            except:
                pass
            
        self._clear_devices()
    
    def _broadcast_loop(self):
        """Continuously broadcast discovery packets"""
        packet = DiscoveryPacket(self.sender_id, MSG_DISCOVERING)
        
        while self.is_running:
            try:
                data = packet.to_bytes()
                # Broadcast to multicast group
                self.socket.sendto(data, (DISCOVERY_GROUP_IP, self.port))
                
                # Also broadcast directly to known peers
                with self.lock:
                    for dev_id in list(self.discovered_devices.keys()):
                        try:
                            self.socket.sendto(data, ('<broadcast>', self.port))
                        except:
                            pass
                            
            except Exception as e:
                if self.is_running:
                    print(f"Broadcast error: {e}")
                
                # Reconnect every 30 seconds on error
                with self.lock:
                    self._clear_devices()
                    
                time.sleep(30)
                
    def _listen_loop(self):
        """Listen for incoming discovery packets from other devices"""
        while self.is_running:
            try:
                data, addr = self.socket.recvfrom(65535)
                parsed = DiscoveryPacket.from_bytes(data)
                
                if parsed and parsed['msg_type'] == MSG_AVAILABLE:
                    # Found a new device
                    sender_id = parsed['sender_id']
                    
                    with self.lock:
                        self.discovered_devices[sender_id] = {
                            'sender_id': sender_id,
                            'timestamp': parsed['timestamp'],
                            'platform': parsed.get('os_platform', 'unknown'),
                            'app_name': parsed.get('app_name', 'AirDrop Clone'),
                            'last_seen': datetime.fromisoformat(parsed['timestamp']),
                            'status': 'discovered'
                        }
                        
                    print(f"✓ Discovered device: {sender_id[:8]}... ({parsed['platform']})")
                    
            except Exception as e:
                if self.is_running:
                    pass  # Expected during shutdown
                
    def get_discovered_devices(self) -> List[Dict]:
        """Get list of discovered devices"""
        with self.lock:
            return list(self.discovered_devices.values())
    
    def _clear_devices(self):
        """Clear discovered devices (called on error or timeout)"""
        current_time = datetime.now()
        stale_threshold = timedelta(seconds=DISCOVERY_INTERVAL_SECONDS * 3)
        
        with self.lock:
            # Remove stale devices (not heard from in a while)
            stale_ids = []
            for sender_id, info in self.discovered_devices.items():
                if current_time - info['last_seen'] > stale_threshold:
                    stale_ids.append(sender_id)
            
            for sid in stale_ids:
                del self.discovered_devices[sid]
    
    def get_sender_id(self) -> str:
        """Get our sender ID (UUID)"""
        return self.sender_id


# =============================================================================
# ANNOTATIONS FOR ANDROID IMPLEMENTATION
# =============================================================================

"""
ANDROID IMPLEMENTATION NOTES:

For Android, implement a similar service using WorkManager:

class AndroidDiscoveryService extends Worker {
    @Override
    public Output getData() {
        // Use ConnectivityManager to join multicast group
        // Send UDP packets via DatagramSocket
        // Return discovered devices list
    }
}

AndroidManifest.xml already has permissions configured:
- INTERNET (for UDP sockets)
- CAMERA (for QR code scanning)
- RECEIVE_BOOT_COMPLETED (for background operation)
"""
