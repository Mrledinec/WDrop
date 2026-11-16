/// Connected device model for saved connections
class ConnectedDevice {
  int? id;
  String deviceId;
  String deviceName;
  String ipAddress;
  bool isSaved; // Whether device is in "saved devices" list
  
  DateTime firstConnectedAt;
  DateTime lastConnectedAt;
  
  ConnectedDevice({
    this.id,
    required this.deviceId,
    required this.deviceName,
    required this.ipAddress,
    this.isSaved = false,
    required this.firstConnectedAt,
    required this.lastConnectedAt,
  });

  factory ConnectedDevice.fromJson(Map<String, dynamic> json) {
    return ConnectedDevice(
      id: json['id'],
      deviceId: json['device_id'] ?? '',
      deviceName: json['device_name'] ?? '',
      ipAddress: json['ip_address'] ?? '',
      isSaved: json['is_saved'] ?? false,
      firstConnectedAt: DateTime.parse(json['first_connected_at']),
      lastConnectedAt: DateTime.parse(json['last_connected_at']),
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'device_id': deviceId,
      'device_name': deviceName,
      'ip_address': ipAddress,
      'is_saved': isSaved,
      'first_connected_at': firstConnectedAt.toIso8601String(),
      'last_connected_at': lastConnectedAt.toIso8601String(),
    };
  }

  factory ConnectedDevice.fromHiveMap(Map<String, dynamic> map) {
    return fromJson(map);
  }
}
