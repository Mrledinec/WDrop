/// File preview screen for viewing downloaded files (images, videos, documents)
import 'package:flutter/material.dart';
import '../../models/transfer_history.dart';

class FilePreviewScreen extends StatelessWidget {
  /// History item to display
  final TransferHistoryItem historyItem;

  const FilePreviewScreen({
    super.key,
    required this.historyItem,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('File Preview'),
        actions: [
          IconButton(
            icon: Icon(Icons.close),
            onPressed: () => Navigator.pop(context),
          ),
        ],
      ),
      body: _buildContent(),
    );
  }

  Widget _buildContent() {
    // Determine file type and build appropriate preview
    switch (historyItem.fileType) {
      case 'image':
        return _buildImagePreview(historyItem);
        
      case 'video':
        return _buildVideoPreview(historyItem);
        
      case 'document':
        return _buildDocumentPreview(historyItem);
        
      default:
        return _buildGenericPreview(historyItem);
    }
  }

  Widget _buildImagePreview(TransferHistoryItem item) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Image placeholder (use Image.network or CachedNetworkImage in production)
          Container(
            width: 300,
            height: 200,
            color: Colors.grey[200],
            child: Icon(Icons.image, size: 64),
          ),
          SizedBox(height: 16),
          
          Text(
            historyItem.filename,
            textAlign: TextAlign.center,
            style: TextStyle(fontWeight: FontWeight.bold),
          ),
          SizedBox(height: 8),
          
          Chip(label: Text(item.fileType)),
          SizedBox(height: 4),
          Chip(label: Text('${_formatSize(item.size)}')),
        ],
      ),
    );
  }

  Widget _buildVideoPreview(TransferHistoryItem item) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 250,
            height: 150,
            color: Colors.grey[800],
            child: Icon(Icons.play_circle, size: 64),
          ),
          SizedBox(height: 16),
          
          Text(historyItem.filename, textAlign: TextAlign.center),
          Chip(label: Text('Video')),
          SizedBox(height: 4),
          Chip(label: Text('${_formatSize(item.size)}'))),
        ],
      ),
    );
  }

  Widget _buildDocumentPreview(TransferHistoryItem item) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 280,
            height: 180,
            color: Colors.orange[50],
            padding: EdgeInsets.all(16),
            child: Icon(Icons.description, size: 48, color: Colors.orange[700]),
          ),
          SizedBox(height: 16),
          
          Text(historyItem.filename, textAlign: TextAlign.center),
          Chip(label: Text('Document')),
          SizedBox(height: 4),
          Chip(label: Text('${_formatSize(item.size)}'))),
        ],
      ),
    );
  }

  Widget _buildGenericPreview(TransferHistoryItem item) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 200,
            height: 200,
            color: Colors.grey[100],
            child: Icon(Icons.folder_open, size: 64),
          ),
          SizedBox(height: 16),
          
          Text(historyItem.filename, textAlign: TextAlign.center),
          Chip(label: Text('Generic file')),
          SizedBox(height: 4),
          Chip(label: Text('${_formatSize(item.size)}'))),
        ],
      ),
    );
  }

  String _formatSize(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1024 * 1024 * 1024) 
      return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }

  /// Open file with default app or show in file manager
  Future<void> openFile() async {
    // Implementation using open_url or platform channels
    print('Opening file: ${historyItem.path}');
  }

  /// Navigate to the original file location in device storage
  void viewInStorage(BuildContext context) {
    showModalBottomSheet(
      context: context,
      builder: (context) => ListTile(
        leading: Icon(Icons.folder),
        title: Text('Show in file manager'),
        onTap: openFile,
      ),
    );
  }
}
