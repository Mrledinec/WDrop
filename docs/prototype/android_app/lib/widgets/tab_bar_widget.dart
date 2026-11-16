/// Tab bar widget for navigation between Send, Receive, Devices and History
import 'package:flutter/material.dart';

class TabBarWidget extends StatelessWidget {
  /// Current active index (0-3)
  final int currentIndex;
  
  /// Callback when tab is tapped
  final VoidCallback? onSendTapped;
  final VoidCallback? onReceiveTapped;
  final VoidCallback? onDevicesTapped;
  final VoidCallback? onHistoryTapped;

  const TabBarWidget({
    super.key,
    required this.currentIndex,
    this.onSendTapped,
    this.onReceiveTapped,
    this.onDevicesTapped,
    this.onHistoryTapped,
  });

  @override
  Widget build(BuildContext context) {
    return NavigationBar(
      selectedIndex: currentIndex,
      onDestinationSelected: (index) {
        switch (index) {
          case 0:
            onSendTapped?.call();
            break;
          case 1:
            onReceiveTapped?.call();
            break;
          case 2:
            onDevicesTapped?.call();
            break;
          case 3:
            onHistoryTapped?.call();
            break;
        }
      },
      destinations: [
        NavigationDestination(
          icon: Icon(Icons.send, size: 28),
          selectedIcon: Icon(Icons.send, size: 28),
          label: 'Send',
        ),
        NavigationDestination(
          icon: Icon(Icons.download, size: 28),
          selectedIcon: Icon(Icons.download, size: 28),
          label: 'Receive',
        ),
        NavigationDestination(
          icon: Icon(Icons.devices, size: 28),
          selectedIcon: Icon(Icons.devices, size: 28),
          label: 'Devices',
        ),
        NavigationDestination(
          icon: Icon(Icons.history, size: 28),
          selectedIcon: Icon(Icons.history, size: 28),
          label: 'History',
        ),
      ],
    );
  }
}

/// Transfer history item widget for displaying recent transfers
class HistoryItemWidget extends StatelessWidget {
  final String filename;
  final int fileSize;
  final DateTime timestamp;
  final bool isSent;
  final VoidCallback? onTap;
  final VoidCallback? onDelete;

  const HistoryItemWidget({
    super.key,
    required this.filename,
    required this.fileSize,
    required this.timestamp,
    required this.isSent,
    this.onTap,
    this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: ListTile(
        leading: _buildIcon(),
        title: Text(
          filename,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(fontWeight: FontWeight.w500),
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(height: 2),
            Text('Sent at ${_formatTime(timestamp)}'),
            Text('${_formatSize(fileSize)}'),
          ],
        ),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            IconButton(
              icon: Icon(Icons.visibility, size: 20),
              onPressed: onTap,
              tooltip: 'Preview',
            ),
            IconButton(
              icon: Icon(Icons.delete_outline, size: 20),
              onPressed: onDelete,
              tooltip: 'Delete from history',
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildIcon() {
    IconData iconData;
    Color color;

    if (filename.endsWith('.jpg') ||
        filename.endsWith('.jpeg') ||
        filename.endsWith('.png')) {
      iconData = Icons.image;
      color = Colors.purple[400];
    } else if (filename.endsWith('.mp4') ||
               filename.endsWith('.avi') ||
               filename.endsWith('.mov')) {
      iconData = Icons.videocam;
      color = Colors.red[400];
    } else if (filename.endsWith('.pdf') ||
               filename.endsWith('.doc') ||
               filename.endsWith('.docx')) {
      iconData = Icons.description;
      color = Colors.orange[400];
    } else {
      iconData = Icons.attach_file;
      color = Colors.blue[400];
    }

    return Icon(iconData, color: color, size: 32);
  }

  String _formatSize(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1024 * 1024 * 1024) return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }

  String _formatTime(DateTime dateTime) {
    final now = DateTime.now();
    if (dateTime.year == now.year &&
        dateTime.month == now.month &&
        dateTime.day == now.day) {
      return '${dateTime.hour.toString().padLeft(2, '0')}:${dateTime.minute.toString().padLeft(2, '0')}';
    } else if (dateTime.year == now.year && dateTime.month == now.month) {
      return '${dateTime.day}/${dateTime.month} ${dateTime.hour.toString().padLeft(2, '0')}:${dateTime.minute.toString().padLeft(2, '0')}';
    } else {
      return '${dateTime.year}-${dateTime.month.toString().padLeft(2, '0')}-${dateTime.day.toString().padLeft(2, '0')} ${dateTime.hour.toString().padLeft(2, '0')}:${dateTime.minute.toString().padLeft(2, '0')}';
    }
  }
}

/// Saved device widget for displaying connected devices
class DeviceWidget extends StatelessWidget {
  final String deviceId;
  final String deviceName;
  final String lastSeen;
  final VoidCallback? onTap;

  const DeviceWidget({
    super.key,
    required this.deviceId,
    required this.deviceName,
    required this.lastSeen,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: Colors.blue[100],
          child: Icon(Icons.laptop, color: Colors.blue[700]),
        ),
        title: Text(deviceName, style: TextStyle(fontWeight: FontWeight.bold)),
        subtitle: Text(lastSeen),
        onTap: onTap,
        trailing: Icon(Icons.chevron_right),
      ),
    );
  }
}
