/// File transfer dialog for sending/receiving files with progress and preview
import 'dart:convert';
import 'package:flutter/material.dart';
import '../../models/transfer_history.dart';

class FileTransferDialog extends StatefulWidget {
  /// Device ID of the server to connect to
  final String deviceId;
  
  /// Mode: 'send' or 'receive'
  final TransferMode mode;

  const FileTransferDialog({
    super.key,
    required this.deviceId,
    required this.mode,
  });

  @override
  State<FileTransferDialog> createState() => _FileTransferDialogState();
}

enum TransferMode { send, receive }

class _FileTransferDialogState extends State<FileTransferDialog> {
  // Simulated progress for UI demo
  double _progress = 0;
  String _status = 'Initializing...';
  
  @override
  void initState() {
    super.initState();
    _simulateTransfer();
  }

  /// Simulate transfer process (replace with real HTTP client)
  Future<void> _simulateTransfer() async {
    await Future.delayed(Duration(milliseconds: 500));
    setState(() => _status = 'Connecting to server...');
    
    await Future.delayed(Duration(seconds: 1));
    setState(() => _status = 'Scanning network...');
    
    if (widget.mode == TransferMode.send) {
      await Future.delayed(Duration(seconds: 2));
      setState(() => _status = 'Select files to send');
    } else {
      await Future.delayed(Duration(seconds: 2));
      setState(() => _status = 'Waiting for incoming connection...');
    }
    
    if (mounted) {
      setState(() => _progress = 100);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(
        widget.mode == TransferMode.send ? 'Send Files' : 'Receive Files',
        style: TextStyle(fontWeight: FontWeight.bold),
      ),
      content: SizedBox(
        width: MediaQuery.of(context).size.width * 0.9,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Status indicator
              _buildStatusIndicator(),
              
              if (widget.mode == TransferMode.send) ...[
                SizedBox(height: 16),
                
                // File selection
                Text('Select files:', style: TextStyle(fontWeight: FontWeight.bold)),
                Divider(),
                _buildFilePickerSection(),
                
                SizedBox(height: 16),
                
                // Progress bar
                _buildProgressIndicator(),
              ] else ...[
                // Receive mode preview area
                _buildPreviewArea(),
              ],
              
              SizedBox(height: 24),
              
              // Status message
              Text(
                _status,
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.grey[600]),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          child: Text('Cancel'),
          onPressed: () => Navigator.pop(context),
        ),
        ElevatedButton(
          child: Text(widget.mode == TransferMode.send ? 'Start Send' : 'Start Receive'),
          onPressed: widget.mode == TransferMode.receive && _progress > 0
              ? () => _handleComplete()
              : null,
        ),
      ],
    );
  }

  Widget _buildStatusIndicator() {
    return Container(
      padding: EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.blue.shade50,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: [
          Icon(Icons.info_outline, size: 24),
          SizedBox(height: 8),
          Text('Connected to: ${widget.deviceId}'),
        ],
      ),
    );
  }

  Widget _buildFilePickerSection() {
    return Container(
      padding: EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('• image.png (1.2 MB) - Preview available'),
          Text('• video.mp4 (45.3 MB) - Preview available'),
          Text('• document.pdf (2.8 MB) - Preview available'),
          SizedBox(height: 8),
          
          Wrap(
            spacing: 8,
            children: [
              ChoiceChip(label: Text('Select All'), selected: false),
              ChoiceChip(label: Text('Deselect All'), selected: false),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildProgressIndicator() {
    return Column(
      children: [
        LinearProgressIndicator(
          value: _progress / 100,
          backgroundColor: Colors.grey[300],
          valueColor: AlwaysStoppedAnimation<Color>(_progress > 50 ? Colors.green : Colors.blue),
        ),
        SizedBox(height: 8),
        
        // Progress detail
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('${(_progress * 10).toInt()}%'),
            Icon(_progress > 50 ? Icons.check_circle : Icons.hourglass_empty, color: Colors.grey[400]),
          ],
        ),
      ],
    );
  }

  Widget _buildPreviewArea() {
    return Container(
      height: 150,
      padding: EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.green.shade50,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.photo_size_select_small, color: Colors.green[700]),
              SizedBox(width: 8),
              Text('Incoming file preview', style: TextStyle(fontWeight: FontWeight.bold)),
            ],
          ),
          SizedBox(height: 8),
          
          Text('file_document.pdf (2.8 MB)'),
          
          SizedBox(height: 4),
          Wrap(
            spacing: 4,
            children: [
              Chip(label: Text('PDF', style: TextStyle(fontSize: 10)), backgroundColor: Colors.orange.shade100),
              Chip(label: Text('2.8 MB'), backgroundColor: Colors.blue.shade50),
            ],
          ),
          
          SizedBox(height: 12),
          
          Row(
            children: [
              Icon(Icons.visibility, size: 16),
              SizedBox(width: 4),
              Text('Tap to preview full file'),
            ],
          ),
        ],
      ),
    );
  }

  void _handleComplete() {
    // Save transfer history and show notification
    if (mounted) {
      setState(() => _progress = 100);
      // Will be handled in NetworkService
    }
  }
}
