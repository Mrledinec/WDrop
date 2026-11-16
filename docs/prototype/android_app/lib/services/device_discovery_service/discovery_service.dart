/// Device Discovery Service for Android (UDP Multicast/Broadcast)
/// 
/// This service handles:
/// - Broadcasting presence to discover other devices
/// - Receiving broadcasts from other devices
/// - Parsing broadcast messages and extracting device info
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter/foundation.dart';
import 'package:permission_handler/permission_handler.dart';
import '../models/discovery_result.dart';

/// Service for discovering devices on local network via UDP broadcast/multicast
class DeviceDiscoveryService {
  /// Singleton instance
  static final DeviceDiscoveryService _instance = DeviceDiscoveryService._internal();
  
  factory DeviceDiscoveryService() => _instance;
  
  DeviceDiscoveryService._internal();

  /// UDP socket for sending/receiving broadcasts
  RawRxDart? _socket;
  
  /// Stream controller for broadcast messages
  final RxStringStream _broadcastMessagesController = RxStringStream();
  
  /// Current status
  String status = 'Ожидание...';
  
  /// Is discovery running
  bool isDiscovering = false;
  
  /// Callback when new device discovered
  Function(DiscoveredDevice)? onDeviceFound;
  
  /// Callback for status updates
  Function(String)? onStatusChange;

  /// Start broadcasting our presence and listen for other devices
  Future<void> startDiscovery() async {
    try {
      // Request network permission (Android 6.0+)
      if (Platform.isAndroid) {
        final status = await Permission.network.request();
        if (!status.isGranted) {
          _updateStatus('Требуется доступ к сети!');
          return;
        }
      }

      // Get local IP address
      final hostname = await InternetAddress.lookup('localhost');
      final localIp = hostname.first.address;
      
      _socket = RawRxDart(socket: Socket()..broadcast = true);
      
      // Send broadcast message to announce our presence
      final broadcastData = jsonEncode({
        'type': 'presence',
        'ip': localIp,
        'timestamp': DateTime.now().toIso8601String(),
      });
      
      _socket!.send(broadcastData);
      
      // Listen for incoming broadcasts on 239.255.255.250 (standard SSDP multicast)
      final multicastSocket = await Socket.connect(
        InternetAddress.anyIPv4,
        1900,
      );
      
      multicastSocket.type = DatagramType.datagram;
      
      // Start listening for broadcasts
      _socket!.listen((event) async {
        try {
          final data = jsonDecode(event) as Map<String, dynamic>;
          final deviceInfo = DiscoveredDevice.fromBroadcastData(data);
          
          onDeviceFound?.call(deviceInfo);
          _broadcastMessagesController.add('Обнаружено устройство: ${deviceInfo.name}');
          
          if (onStatusChange != null) {
            onStatusChange!.call('✓ Обнаружено: ${deviceInfo.name} (${deviceInfo.ip})');
          }
        } catch (e) {
          _updateStatus('Ошибка обработки сообщения: $e');
        }
      }, onError: (error) {
        _updateStatus('Ошибка приёма UDP: $error');
      });
      
      _socket!.close.listen((_) async {
        await multicastSocket.close();
      }, onError: (_) {}, onDone: () {}, cancelOnError: true);
      
    } catch (e) {
      _updateStatus('Ошибка запуска discovery: $e');
    }
  }

  /// Send broadcast to discover other devices
  Future<void> sendBroadcast() async {
    try {
      final hostname = await InternetAddress.lookup('localhost');
      final localIp = hostname.first.address;
      
      final broadcastData = jsonEncode({
        'type': 'presence',
        'ip': localIp,
        'timestamp': DateTime.now().toIso8601String(),
      });
      
      _socket!.send(broadcastData);
      _updateStatus('Отправлено объявление о себе');
    } catch (e) {
      _updateStatus('Ошибка отправки: $e');
    }
  }

  /// Stop discovery service
  Future<void> stopDiscovery() async {
    try {
      _socket?.close();
      _socket = null;
      isDiscovering = false;
      _updateStatus('Discovery остановлен');
    } catch (e) {
      _updateStatus('Ошибка остановки: $e');
    }
  }

  /// Get broadcast messages stream
  RxStringStream get broadcastMessages => _broadcastMessagesController;

  void _updateStatus(String msg) {
    status = msg;
    onStatusChange?.call(msg);
  }

  @override
  void dispose() {
    stopDiscovery();
  }
}

/// Model for discovered device from UDP broadcast
class DiscoveredDevice {
  final String ip;
  final String name;
  final DateTime timestamp;
  
  DiscoveredDevice({
    required this.ip,
    required this.name,
    required this.timestamp,
  });
  
  /// Parse from UDP broadcast message
  factory DiscoveredDevice.fromBroadcastData(Map<String, dynamic> data) {
    return DiscoveredDevice(
      ip: data['ip'] ?? 'unknown',
      name: data['name'] ?? 'Device ${data['ip']}',
      timestamp: DateTime.parse(data['timestamp'] ?? DateTime.now().toIso8601String()),
    );
  }
  
  /// Generate connection URL for this device
  String get connectionUrl {
    final base64Id = _generateBase64Id(ip);
    return 'http://$ip:8000/connect?device_id=$base64Id&name=$name';
  }

  String _generateBase64Id(String ip) {
    // Simple base64-like encoding for device ID
    final bytes = utf8.encode(ip);
    return base64Encode(bytes).substring(0, 20);
  }

  @override
  String toString() {
    return 'DiscoveredDevice(ip: $ip, name: $name, timestamp: $timestamp)';
  }
}

/// Simple Rx implementation for Flutter streams
class RxStringStream<T> extends Stream<T> with ChangeNotifier {
  T? _value;
  List<String> _history = [];
  
  bool get hasValue => _value != null;
  String get value => _value ?? '';
  
  @override
  StreamSubscription<T> listen(
    StreamHandler<T> handler, {
    void Function()? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) {
    return Stream.fromIterable(_history).listen(handler, onError: onError, onDone: onDone, cancelOnError: cancelOnError);
  }
  
  @override
  cast<T> as<T>() => cast<T>();
}
