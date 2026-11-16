/// Connection dialog showing QR code and list of previously connected devices
import 'package:flutter/material.dart';
import '../../models/connected_device.dart';

class ConnectionDialog extends StatelessWidget {
  /// Unique device ID for this client
  final String deviceId;
  
  /// Device name (display name)
  final String deviceName;
  
  /// Base URL for the server (will be discovered dynamically)
  final String? baseUrlHint;

  const ConnectionDialog({
    super.key,
    required this.deviceId,
    required this.deviceName,
    this.baseUrlHint,
  });

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('Connect to Server'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // QR Code section
            _buildQRCodeSection(),
            
            SizedBox(height: 16),
            
            // Manual connection section
            Text('Or connect manually:', style: TextStyle(fontWeight: FontWeight.bold)),
            SizedBox(height: 8),
            
            TextField(
              decoration: InputDecoration(
                hintText: 'http://192.168.x.x:8000',
                prefixIcon: Icon(Icons.globe),
                border: OutlineInputBorder(),
              ),
              controller: TextEditingController(text: baseUrlHint ?? ''),
            ),
            
            SizedBox(height: 16),
            
            // Previously connected devices section
            Text('Previously connected devices:', style: TextStyle(fontWeight: FontWeight.bold)),
            ...getPreviousConnections(context).map((device) => _buildSavedDeviceItem(device)),
          ],
        ),
      ),
      actions: [
        TextButton(
          child: Text('Cancel'),
          onPressed: () => Navigator.pop(context),
        ),
        ElevatedButton(
          child: Text('Connect'),
          onPressed: () {
            // Handle connection logic
            Navigator.pop(context, true);
          },
        ),
      ],
    );
  }

  Widget _buildQRCodeSection() {
    return Padding(
      padding: EdgeInsets.all(8),
      child: Container(
        width: 200,
        height: 200,
        decoration: BoxDecoration(
          color: Colors.white,
          border: Border.all(color: Colors.black, width: 2),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Center(
          child: Text('QR Code Placeholder', style: TextStyle(fontSize: 14)),
        ),
      ),
    );
  }

  Widget _buildSavedDeviceItem(String deviceIp) {
    return ListTile(
      leading: Icon(Icons.computer),
      title: Text('Server at $deviceIp'),
      subtitle: Text('Click to connect'),
      onTap: () => Navigator.pop(context, deviceIp),
    );
  }

  /// Placeholder for getting previously connected devices
  /// In real implementation, this would read from Hive or shared database
  List<String> getPreviousConnections(BuildContext context) {
    return ['192.168.1.100', '192.168.1.101']; // Placeholder
  }

  /// Generate QR code URL for sharing
  String get qrUrl {
    // Format: http://<ip>:8000/qr/connect?device_id=<id>&name=<name>
    return 'http://placeholder.com/qr/connect?device_id=$deviceId&name=${Uri.encodeComponent(deviceName)}';
  }

  /// Share QR code via system share sheet
  Future<void> shareQRCode() async {
    // Implementation using share_plus package
    print('Share QR code');
  }
}
