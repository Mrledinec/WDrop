/// Device discovery service using QR codes and IP scanning
import 'package:qr_flutter/qr_flutter.dart';
import 'package:share_plus/share_plus.dart';
import 'dart:async';
import 'dart:convert';

/// DiscoveryService handles device discovery via QR code and manual IP entry
class DiscoveryService {
  /// Unique device identifier (from shared DB)
  final String deviceId;
  
  /// Device name from settings
  final String deviceName;
  
  /// Network interface for IP scanning
  final List<NetworkInterface> localNetworks;

  /// Creates discovery service
  DiscoveryService({
    required this.deviceId,
    required this.deviceName,
    required this.localNetworks,
  });

  /// Generate QR code URL for device discovery
  /// 
  /// The QR code contains the server URL and device info for first-time connection
  String get qrCodeUrl {
    // Format: http://<ip>:8000/qr/connect?device_id=<id>&name=<name>
    // Users will enter password separately on their device
    return 'http://${localNetworks.first.ip}:${config.port}/qr/connect?device_id=$deviceId&name=${Uri.encodeComponent(deviceName)}';
  }

  /// Convert QR code URL to shareable text
  String get qrText => qrCodeUrl;

  /// Get QR code widget for display in app
  Widget buildQrWidget() {
    return Stack(
      alignment: Alignment.center,
      children: [
        Container(
          width: 200,
          height: 200,
          decoration: BoxDecoration(
            color: Colors.white,
            border: Border.all(color: Colors.black, width: 2),
            borderRadius: BorderRadius.circular(10),
          ),
          child: QrImageView(
            data: qrCodeUrl,
            version: QrVersions.auto,
            size: 200.0,
          ),
        ),
        Positioned(
          bottom: -20,
          child: Text(
            'Scan to connect',
            style: TextStyle(color: Colors.grey, fontSize: 14),
          ),
        ),
      ],
    );
  }

  /// Share QR code to other devices via SMS, email, etc.
  Future<void> shareQrCode() async {
    await Share.share(qrText);
  }

  /// Start IP scanning on local network
  /// 
  /// Scans available networks and checks for running AirDrop servers
  Stream<List<DiscoveredDevice>> startScanning({int intervalMs = 2000}) async* {
    // Initial scan
    final devices = await _scanNetworks();
    yield devices;

    // Periodic scanning
    Timer.periodic(Duration(milliseconds: intervalMs), (timer) async {
      try {
        final newDevices = await _scanNetworks();
        if (newDevices != devices) {
          yield newDevices;
          devices.clear(); // Clear old results
        }
      } catch (e) {
        print('Scan error: $e');
      }
    });
  }

  /// Manual scan of local networks
  Future<List<DiscoveredDevice>> _scanNetworks() async {
    final discovered = <DiscoveredDevice>[];

    for (final network in localNetworks) {
      try {
        // Check if port is open using HTTP HEAD request
        final uri = Uri.parse('http://${network.ip}:${config.port}/');
        
        final response = await http.get(uri, headers: {
          'User-Agent': 'AirDrop-Clone/1.0',
        }).catchError((_) => null);

        if (response?.statusCode == 200) {
          discovered.add(DiscoveredDevice(
            ip: network.ip,
            port: config.port,
            deviceName: 'AirDrop Server',
            isOnline: true,
          ));
        }
      } catch (e) {
        // Skip this network if unreachable
      }
    }

    return discovered;
  }

  /// Get QR code image bytes for display
  Future<List<int>> getQrImageBytes() async {
    final qrSvg = buildQrWidget();
    // Convert to SVG bytes for display
    return ['<svg>...</svg>'.codeUnits]; // Placeholder - implement actual conversion
  }

  /// Get current discovered devices list
  List<DiscoveredDevice> get discoveredDevices => _discovered;

  /// Manual scan trigger
  Future<List<DiscoveredDevice>> manualScan() async {
    return _scanNetworks();
  }

  StreamController<List<DiscoveredDevice>>? _controller;
  List<DiscoveredDevice> _discovered = [];

  /// Start/stop scanning service
  void toggleScanning(bool enabled) {
    if (enabled) {
      _controller = StreamController<List<DiscoveredDevice>>(sync: true);
      startScanning().listen((devices) {
        _discovered = devices;
        _controller!.add(devices);
      });
    } else {
      _controller?.close();
      _discovered = [];
    }
  }

  /// Get QR code URL for current network
  String getConnectUrl() {
    if (localNetworks.isEmpty) return '';
    return 'http://${localNetworks.first.ip}:${config.port}/qr/connect?device_id=$deviceId&name=${Uri.encodeComponent(deviceName)}';
  }

  @override
  void dispose() {
    toggleScanning(false);
  }
}

/// Discovered device from network scan
class DiscoveredDevice {
  final String ip;
  final int port;
  final String deviceName;
  final bool isOnline;

  DiscoveredDevice({
    required this.ip,
    required this.port,
    required this.deviceName,
    required this.isOnline,
  });

  String get fullUrl => 'http://$ip:$port';
}
