import 'package:flutter/services.dart';

class TransferPlatform {
  static const _channel = MethodChannel('local.transfer/control');

  Future<Map<String, dynamic>> state() async =>
      await _channel.invokeMapMethod<String, dynamic>('state') ?? {};

  Future<Map<String, dynamic>> historyFileInfo(String id) async =>
      await _channel.invokeMapMethod<String, dynamic>('historyFileInfo', {
        'id': id,
      }) ??
      {};

  Future<void> run(String method, [Map<String, Object>? values]) async {
    await _channel.invokeMethod<Object>(method, values);
  }
}
