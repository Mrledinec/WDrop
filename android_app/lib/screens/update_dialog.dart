import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

class UpdateDialog extends StatefulWidget {
  const UpdateDialog({super.key});

  @override
  State<UpdateDialog> createState() => _UpdateDialogState();
}

class _UpdateDialogState extends State<UpdateDialog> {
  static const _channel = MethodChannel('local.transfer/control');
  String? _currentVersion;
  String? _availableVersion;
  String _status = 'Проверяем обновления…';
  bool _busy = true;

  @override
  void initState() {
    super.initState();
    _check();
  }

  Future<void> _check() async {
    setState(() {
      _busy = true;
      _availableVersion = null;
      _status = 'Проверяем обновления…';
    });
    try {
      final current = await _channel.invokeMethod<String>('updateVersion');
      if (!mounted) return;
      setState(() => _currentVersion = current);
      final available = await _channel.invokeMethod<String>('checkUpdate');
      if (!mounted) return;
      setState(() {
        _availableVersion = available;
        _status = available == null
            ? 'Установлена актуальная версия.'
            : 'Доступна версия $available.';
      });
    } on PlatformException catch (error) {
      if (mounted) {
        setState(() {
          _status = error.message ?? 'Не удалось проверить обновление.';
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _install() async {
    setState(() {
      _busy = true;
      _status = 'Готовим установку…';
    });
    try {
      final opened = await _channel.invokeMethod<bool>('installUpdate');
      if (!mounted) return;
      setState(() {
        _status = opened == true
            ? 'Подтвердите обновление в установщике Android.'
            : 'Разрешите установку из этого источника, вернитесь и снова нажмите «Установить».';
      });
    } on PlatformException catch (error) {
      if (mounted) {
        setState(() {
          _status = error.message ?? 'Не удалось установить обновление.';
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_busy,
      child: AlertDialog(
        scrollable: true,
        title: const Text('Обновления'),
        content: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (_currentVersion case final version?)
              Text('Текущая версия: $version'),
            const SizedBox(height: 8),
            Text(_status),
          ],
        ),
        actions: [
          TextButton(
            onPressed: _busy ? null : () => Navigator.of(context).pop(),
            child: const Text('Закрыть'),
          ),
          TextButton(
            onPressed: _busy ? null : _check,
            child: const Text('Проверить обновление'),
          ),
          if (_availableVersion != null)
            FilledButton(
              onPressed: _busy ? null : _install,
              child: const Text('Установить'),
            ),
        ],
      ),
    );
  }
}
