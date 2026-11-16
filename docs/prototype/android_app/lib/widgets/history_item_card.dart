import 'package:flutter/material.dart';
import '../models/transfer_history.dart';

/// Widget for displaying a single file transfer in history list
class HistoryItemCard extends StatelessWidget {
  final TransferHistory item;
  final VoidCallback? onTap;
  final bool showPreview;
  
  const HistoryItemCard({
    super.key,
    required this.item,
    this.onTap,
    this.showPreview = false,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      elevation: 2,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(12.0),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Icon/Preview area
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      item.filename ?? 'Без имени',
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 16,
                        color: Theme.of(context).textTheme.bodyLarge?.color,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 4),
                    
                    // File size and type
                    Row(
                      children: [
                        _buildSizeChip(item.size),
                        const SizedBox(width: 8),
                        _buildTypeIcon(context, item.mimeType),
                      ],
                    ),
                  ],
                ),
              ),
              
              // Status badge on the right
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 6,
                    ),
                    decoration: BoxDecoration(
                      color: item.status == 'completed'
                          ? Colors.green.shade50
                          : (item.status == 'failed' 
                              ? Colors.red.shade50 
                              : Colors.orange.shade50),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          item.status == 'completed'
                              ? Icons.check_circle_outline
                              : (item.status == 'failed'
                                  ? Icons.error_outline
                                  : Icons.pending),
                          color: item.status == 'completed'
                              ? Colors.green[600]
                              : (item.status == 'failed'
                                  ? Colors.red[600]
                                  : Colors.orange[600]),
                          size: 18,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          item.status,
                          style: TextStyle(
                            fontSize: 11,
                            color: item.status == 'completed'
                                ? Colors.green[900]
                                : (item.status == 'failed'
                                    ? Colors.red[900]
                                    : Colors.orange[900]),
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 4),
                  
                  // Timestamp and actions
                  Row(
                    children: [
                      Text(
                        _formatTimestamp(item.timestamp),
                        style: TextStyle(
                          fontSize: 10,
                          color: Colors.grey[600],
                        ),
                      ),
                      const Spacer(),
                      if (item.path != null && showPreview)
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 4,
                          ),
                          decoration: BoxDecoration(
                            color: Colors.blue.shade50,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                Icons.visibility_outlined,
                                size: 14,
                                color: Colors.blue[700],
                              ),
                              const SizedBox(width: 4),
                              Text(
                                'Превью',
                                style: TextStyle(
                                  fontSize: 11,
                                  color: Colors.blue[900],
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ],
                          ),
                        ),
                    ],
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSizeChip(int size) {
    final sizeText = _formatFileSize(size);
    
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: Colors.grey.shade100,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        sizeText,
        style: TextStyle(
          fontSize: 11,
          color: Colors.grey[700],
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }

  Widget _buildTypeIcon(BuildContext context, String? mimeType) {
    IconData icon;
    
    switch (mimeType) {
      case 'image/*':
        icon = Icons.image_outlined;
        break;
      case 'video/*':
        icon = Icons.video_library_outlined;
        break;
      case 'audio/*':
        icon = Icons.audiotrack_outlined;
        break;
      case 'text/*':
        icon = Icons.description_outlined;
        break;
      case 'application/pdf':
        icon = Icons.insert_drive_file_outlined;
        break;
      default:
        icon = Icons.file_outlined;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: Colors.blue.shade50,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Icon(icon, size: 16, color: Colors.blue[700]),
    );
  }

  String _formatSize(int bytes) {
    if (bytes < 1024) return '$bytes B';
    else if (bytes < 1048576) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    else if (bytes < 1073741824) return '${(bytes / 1048576).toStringAsFixed(1)} MB';
    else return '${(bytes / 1073741824).toStringAsFixed(1)} GB';
  }

  String _formatFileSize(int size) {
    // Simplified format (should use actual MIME type for better icons)
    if (size > 1073741824) return '${(size / 1073741824).toStringAsFixed(1)} GB';
    else if (size > 1048576) return '${(size / 1048576).toStringAsFixed(1)} MB';
    else return '${(size / 1024).toStringAsFixed(1)} KB';
  }

  String _formatTimestamp(DateTime timestamp) {
    final now = DateTime.now();
    final diff = now.difference(timestamp);
    
    if (diff.inDays > 365) {
      return '${(diff.inDays / 365).floor()} год назад';
    } else if (diff.inDays > 30) {
      return '${(diff.inDays / 30).floor()} мес. назад';
    } else if (diff.inDays > 0) {
      return '${diff.inDays} дн. назад';
    } else if (diff.inHours > 0) {
      return '${diff.inHours} ч. назад';
    } else if (diff.inMinutes > 0) {
      return '${diff.inMinutes} мин. назад';
    } else {
      return 'Сегодня, ${timestamp.hour.toString().padLeft(2, '0')}:${timestamp.minute.toString().padLeft(2, '0')}';
    }
  }
}
