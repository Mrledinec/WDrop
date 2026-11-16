/// WorkManager Registrar for Background File Reception
/// Handles registration and configuration of background workers
import 'dart:convert';
import 'package:workmanager/workmanager.dart';

class WorkManagerRegistrar {
  static final WorkManagerRegistrar _instance = WorkManagerRegistrar._internal();
  
  factory WorkManagerRegistrar() => _instance;
  
  WorkManagerRegistrar._internal();
  
  /// Register the background worker callback
  void registerWorker() {
    Workmanager().initialize(
      callbackDispatcher: (id, data) async {
        print('WorkManager received notification');
        
        try {
          // Parse incoming file data
          final intentData = jsonDecode(data ?? '{}') as Map<String, dynamic>;
          
          print('Received: ${intentData['device_id']}');
          
          // Trigger foreground notification to alert user
          if (intentData['status'] == 'uploaded') {
            _showIncomingFileNotification(
              deviceName: intentData['device_name'] ?? 'Device',
              filename: intentData['filename'],
            );
          }
          
          return 'OK';
        } catch (e) {
          print('Error processing work callback: $e');
          return 'ERROR: $e';
        }
      },
      // Use coroutines or threads based on implementation
      executor: Workmanager().executor,
    );
    
    // Register periodic task (optional - for automatic checks)
    Workmanager().registerPeriodic(
      uniqueName: 'file_download_checker',
      tasks: () => ['download_file'],
      initialDelay: const Duration(minutes: 1),
      frequency: const Duration(minutes: 5),
      constraints: Constraints(
        networkType: NetworkType.not_required,
        requiredNetworkType: NetworkType.not_required,
      ),
    );
  }
  
  /// Trigger manual file download task
  void triggerFileDownload(String taskId) {
    Workmanager().execute(
      uniqueName: taskId,
      data: 'device_id=example123&status=uploaded',
      topics: ['file_transfer'],
    );
  }
  
  /// Show incoming file notification (placeholder for real implementation)
  Future<void> _showIncomingFileNotification({
    required String deviceName,
    required String filename,
  }) async {
    // In production, would use flutter_local_notifications package
    print('Incoming file from: $deviceName - File: $filename');
    
    // Create notification channel (Android 8.0+)
    if (!await Workmanager().isChannelCreated('airdrop-incoming')) {
      await Workmanager().createNotificationChannel(
        id: 'airdrop-incoming',
        name: 'AirDrop Incoming Files',
        description: 'Notifications for incoming files via AirDrop Clone',
        importance: Importance.high,
      );
    }
    
    // Show notification (placeholder - needs flutter_local_notifications)
    print('Would show notification for: $filename from $deviceName');
  }
}

/// Extension to check if channel exists
extension WorkmanagerChannel on Workmanager {
  Future<bool> isChannelCreated(String id) async {
    try {
      await getNotificationChannels();
      return channels.any((channel) => channel.id == id);
    } catch (e) {
      return false;
    }
  }
}