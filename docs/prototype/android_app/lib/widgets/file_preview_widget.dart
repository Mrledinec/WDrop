/// File preview widget for displaying file thumbnails and previews in list views
import 'package:flutter/material.dart';
import '../../models/transfer_history.dart';

class FilePreviewWidget extends StatelessWidget {
  /// File history item to display
  final TransferHistoryItem file;
  
  /// Callback when file is tapped
  final VoidCallback onTap;
  
  const FilePreviewWidget({
    super.key,
    required this.file,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: EdgeInsets.symmetric(horizontal: 4, vertical: 2),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(8),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.1),
            blurRadius: 4,
            offset: Offset(0, 2),
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(8),
          onTap: onTap,
          child: Padding(
            padding: EdgeInsets.all(8),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Preview thumbnail
                Container(
                  width: 60,
                  height: 60,
                  decoration: BoxDecoration(
                    color: _getFileColor(),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Icon(_getFileIcon(), size: 32, color: Colors.white.withOpacity(0.9)),
                ),
                
                SizedBox(width: 12),
                
                // File info
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        file.filename,
                        style: TextStyle(fontWeight: FontWeight.w500, fontSize: 14),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      SizedBox(height: 2),
                      
                      Row(
                        children: [
                          Icon(Icons.folder_open, size: 12, color: Colors.grey[600]),
                          SizedBox(width: 4),
                          Text(
                            '${_formatSize(file.size)}',
                            style: TextStyle(color: Colors.grey[600], fontSize: 12),
                          ),
                        ],
                      ),
                      
                      SizedBox(height: 2),
                      
                      Row(
                        children: [
                          Icon(Icons.access_time, size: 12, color: Colors.grey[600]),
                          SizedBox(width: 4),
                          Text(
                            _formatDate(file.timestamp),
                            style: TextStyle(color: Colors.grey[600], fontSize: 11),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  IconData _getFileIcon() {
    if (file.filename.endsWith('.jpg') || file.filename.endsWith('.jpeg')) return Icons.photo;
    if (file.filename.endsWith('.png')) return Icons.image;
    if (file.filename.endsWith('.gif')) return Icons.gif;
    if (file.filename.endsWith('.mp4') || file.filename.endsWith('.avi')) return Icons.video_library;
    if (file.filename.endsWith('.pdf')) return Icons.description;
    if (file.filename.endsWith('.doc') || file.filename.endsWith('.docx')) return Icons.document_scanner;
    if (file.filename.endsWith('.zip') || file.filename.endsWith('.rar')) return Icons.unarchive;
    if (file.filename.endsWith('.exe')) return Icons.computer;
    
    return Icons.attach_file;
  }

  Color _getFileColor() {
    switch (_getFileIcon()) {
      case Icons.photo:
      case Icons.image:
        return Colors.purple[200]!;
      case Icons.video_library:
        return Colors.red[200]!;
      case Icons.description:
        return Colors.orange[200]!;
      case Icons.document_scanner:
        return Colors.blue[200]!;
      case Icons.unarchive:
        return Colors.grey[300]!;
      case Icons.computer:
        return Colors.teal[200]!;
      default:
        return Colors.blue[100]!;
    }
  }

  String _formatSize(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1024 * 1024 * 1024) return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }

  String _formatDate(DateTime dateTime) {
    final now = DateTime.now();
    if (dateTime.year == now.year &&
        dateTime.month == now.month &&
        dateTime.day == now.day) {
      return '${dateTime.hour.toString().padLeft(2, '0')}:${dateTime.minute.toString().padLeft(2, '0')}';
    } else if (dateTime.year == now.year && dateTime.month == now.month) {
      return '${dateTime.day}/${dateTime.month} ${dateTime.hour.toString().padLeft(2, '0')}:${dateTime.minute.toString().padLeft(2, '0')}';
    } else {
      return '${dateTime.day}/${dateTime.month}/${dateTime.year}';
    }
  }
}

/// List of connected devices widget for displaying server connections
class ConnectedDevicesWidget extends StatelessWidget {
  /// List of connected device IDs
  final List<String> deviceIds;
  
  /// List of device names
  final List<String> deviceNames;
  
  const ConnectedDevicesWidget({
    super.key,
    required this.deviceIds,
    required this.deviceNames,
  });

  @override
  Widget build(BuildContext context) {
    if (deviceIds.isEmpty) {
      return Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Column(
            children: [
              Icon(Icons.laptop_mac, size: 48, color: Colors.grey[400]),
              SizedBox(height: 16),
              Text('No devices connected', style: TextStyle(color: Colors.grey[500], fontSize: 16)),
            ],
          ),
        ),
      );
    }

    return ListView.builder(
      shrinkWrap: true,
      physics: NeverScrollableScrollPhysics(),
      itemCount: deviceIds.length,
      itemBuilder: (context, index) {
        final deviceId = deviceIds[index];
        final deviceName = deviceNames[index];
        
        return Card(
          margin: EdgeInsets.symmetric(horizontal: 12, vertical: 4),
          child: ListTile(
            leading: CircleAvatar(
              backgroundColor: Colors.green[50],
              child: Icon(Icons.laptop_windows, color: Colors.green[700]),
            ),
            title: Text(deviceName, style: TextStyle(fontWeight: FontWeight.bold)),
            subtitle: Text('ID: ${deviceId.substring(0, 8)}...'),
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.check_circle, size: 20, color: Colors.green[600]),
                SizedBox(width: 8),
                Chip(
                  label: Text('Online', style: TextStyle(fontSize: 11)),
                  backgroundColor: Colors.green[50],
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
