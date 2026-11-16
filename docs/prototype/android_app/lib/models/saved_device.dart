/// Device model for saved connections (Android)
class SavedDevice {
  final String id;
  final String name;
  final String ip;
  final DateTime? lastConnected;
  
  const SavedDevice({
    required this.id,
    required this.name,
    required this.ip,
    this.lastConnected,
  });

  factory SavedDevice.fromJson(Map<String, dynamic> json) {
    return SavedDevice(
      id: json['id'] ?? '',
      name: json['name'] ?? 'Unknown',
      ip: json['ip'] ?? '',
      lastConnected: json['last_connected'] != null 
          ? DateTime.parse(json['last_connected']) 
          : null,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'ip': ip,
      'last_connected': lastConnected?.toIso8601String(),
    };
  }

  SavedDevice copyWith({
    String? id,
    String? name,
    String? ip,
    DateTime? lastConnected,
  }) {
    return SavedDevice(
      id: id ?? this.id,
      name: name ?? this.name,
      ip: ip ?? this.ip,
      lastConnected: lastConnected ?? this.lastConnected,
    );
  }

  @override
  String toString() {
    return 'SavedDevice(id: $id, name: $name, ip: $ip)';
  }
}