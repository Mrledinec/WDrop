/// Transfer history model matching shared database schema
class TransferHistory {
  int? id;
  String deviceId;
  String deviceName;
  String ipAddress;
  DateTime createdAt;
  
  // File info (only for received files)
  String? fileName;
  String? filePath;
  int? fileSize;
  DateTime? transferredAt;

  TransferHistory({
    this.id,
    required this.deviceId,
    required this.deviceName,
    required this.ipAddress,
    required this.createdAt,
    this.fileName,
    this.filePath,
    this.fileSize,
    this.transferredAt,
  });

  factory TransferHistory.fromJson(Map<String, dynamic> json) {
    return TransferHistory(
      id: json['id'],
      deviceId: json['device_id'] ?? '',
      deviceName: json['device_name'] ?? '',
      ipAddress: json['ip_address'] ?? '',
      createdAt: DateTime.parse(json['created_at']),
      fileName: json['file_name'] as String?,
      filePath: json['file_path'] as String?,
      fileSize: json['file_size'] as int?,
      transferredAt: json['transferred_at'] != null 
          ? DateTime.parse(json['transferred_at']) 
          : null,
    );
  }

  Map<String, dynamic> toJson() {
    final map = <String, dynamic>{
      'device_id': deviceId,
      'device_name': deviceName,
      'ip_address': ipAddress,
      'created_at': createdAt.toIso8601String(),
      if (fileName != null) 'file_name': fileName,
      if (filePath != null) 'file_path': filePath,
      if (fileSize != null) 'file_size': fileSize,
      if (transferredAt != null) 'transferred_at': transferredAt.toIso8601String(),
    };
    return map;
  }

  // Copy with only file info (for received files)
  TransferHistory asReceivedFile(Map<String, dynamic> fileInfo) {
    return TransferHistory(
      id: this.id,
      deviceId: this.deviceId,
      deviceName: this.deviceName,
      ipAddress: this.ipAddress,
      createdAt: this.createdAt,
      fileName: fileInfo['file_name'] as String?,
      filePath: fileInfo['file_path'] as String?,
      fileSize: fileInfo['file_size'] as int?,
      transferredAt: DateTime.now(),
    );
  }

  // Convert to Map for Hive storage
  Map<String, dynamic> toHiveMap() {
    return toJson();
  }

  factory TransferHistory.fromHiveMap(Map<String, dynamic> map) {
    return fromJson(map);
  }
}
