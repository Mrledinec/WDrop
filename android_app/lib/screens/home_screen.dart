import 'dart:async';

import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../services/network_service.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _platform = TransferPlatform();
  Map<String, dynamic> _state = {};
  Timer? _timer;
  bool _refreshing = false;
  bool _pairing = false;
  bool _showDiscovery = false;
  DateTime? _searchEnds;

  @override
  void initState() {
    super.initState();
    unawaited(_refresh());
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => _refresh());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    if (_refreshing) return;
    _refreshing = true;
    try {
      final state = await _platform.state();
      if (mounted) setState(() => _state = state);
    } on PlatformException {
      // A later refresh can recover if the activity is resuming.
    } finally {
      _refreshing = false;
    }
  }

  Future<void> _run(String method, [Map<String, Object>? options]) async {
    try {
      await _platform.run(method, options);
      await _refresh();
    } on PlatformException catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.message ?? 'Операция не выполнена')),
      );
    }
  }

  Iterable<Map<Object?, Object?>> _items(String key) =>
      (_state[key] as List? ?? []).cast<Map<Object?, Object?>>();

  Future<String?> _input(String title, String label, String initial) async {
    var value = initial;
    final answer = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: TextFormField(
          initialValue: initial,
          autofocus: true,
          decoration: InputDecoration(labelText: label),
          onChanged: (text) => value = text,
          onFieldSubmitted: (text) => Navigator.pop(context, text),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, value),
            child: const Text('Сохранить'),
          ),
        ],
      ),
    );
    return answer?.trim();
  }

  Future<void> _limit() async {
    final input = await _input(
      'Лимит приёма',
      'Размер в МиБ, 0 — без ограничения',
      (_state['limit'] ?? 2048).toString(),
    );
    if (input == null) return;
    final value = int.tryParse(input);
    if (value == null || value < 0 || value > 1048576) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Укажите число от 0 до 1048576')),
        );
      }
      return;
    }
    await _run('limit', {'value': value});
  }

  Future<void> _pair(String? code) async {
    if (code == null || code.isEmpty || _pairing) return;
    setState(() => _pairing = true);
    await _run('pair', {'code': code});
    if (mounted) setState(() => _pairing = false);
  }

  Future<void> _scan() async {
    final code = await Navigator.of(
      context,
    ).push<String>(MaterialPageRoute(builder: (context) => const _QrScreen()));
    if (mounted) await _pair(code);
  }

  Future<void> _findComputers() async {
    setState(() {
      _showDiscovery = true;
      _searchEnds = DateTime.now().add(const Duration(seconds: 6));
    });
    await _run('discover');
  }

  Future<void> _pairFound(Map<Object?, Object?> device) async {
    final code = await _input(
      'Подключение к ПК',
      'Код из окна сопряжения на ПК',
      '',
    );
    if (!mounted || code == null || code.isEmpty || _pairing) return;
    setState(() => _pairing = true);
    await _run('pairDiscovered', {'id': device['id'] as String, 'code': code});
    if (mounted) setState(() => _pairing = false);
  }

  Future<void> _paste() async {
    final clipboard = await Clipboard.getData(Clipboard.kTextPlain);
    if (!mounted) return;
    final code = await _input(
      'Код подключения',
      'Вставьте код с ПК',
      clipboard?.text ?? '',
    );
    if (mounted) await _pair(code);
  }

  Future<void> _chooseReceiver({required bool shared}) async {
    final peers = _items('peers').toList();
    if (peers.isEmpty) return;
    final id = await showDialog<String>(
      context: context,
      builder: (context) => SimpleDialog(
        title: const Text('Куда отправить'),
        children: [
          for (final peer in peers)
            SimpleDialogOption(
              onPressed: () => Navigator.pop(context, peer['id'] as String),
              child: ListTile(
                leading: const Icon(Icons.computer_outlined),
                title: Text(peer['name'].toString()),
                subtitle: Text(peer['host'].toString()),
                contentPadding: EdgeInsets.zero,
              ),
            ),
        ],
      ),
    );
    if (mounted && id != null) {
      await _run(shared ? 'sendShared' : 'send', {'id': id});
    }
  }

  String _size(Object? size) {
    final bytes = size as int? ?? 0;
    if (bytes >= 1073741824) {
      return '${(bytes / 1073741824).toStringAsFixed(2)} ГиБ';
    }
    if (bytes >= 1048576) return '${(bytes / 1048576).toStringAsFixed(1)} МиБ';
    if (bytes >= 1024) return '${(bytes / 1024).toStringAsFixed(1)} КиБ';
    return '$bytes Б';
  }

  Widget _device(Map<Object?, Object?> peer) {
    final id = peer['id'] as String;
    final trusted = peer['trusted'] == true;
    final status = peer['online'] == true ? ' · в сети' : ' · не в сети';
    return ListTile(
      title: Text(peer['name'].toString()),
      subtitle: Text('${peer['host']}$status'),
      leading: const Icon(Icons.computer_outlined),
      trailing: PopupMenuButton<String>(
        tooltip: 'Настройки устройства',
        onSelected: (action) async {
          switch (action) {
            case 'trust':
              await _run('trust', {'id': id, 'value': !trusted});
            case 'rename':
              final name = await _input(
                'Переименовать компьютер',
                'Имя в списке',
                peer['name'].toString(),
              );
              if (name != null) await _run('rename', {'id': id, 'name': name});
            case 'address':
              final host = await _input(
                'Адрес ПК',
                'IPv4-адрес',
                peer['host'].toString(),
              );
              if (host != null) await _run('address', {'id': id, 'host': host});
            case 'remove':
              await _run('remove', {'id': id});
          }
        },
        itemBuilder: (context) => [
          CheckedPopupMenuItem(
            value: 'trust',
            checked: trusted,
            child: const Text('Принимать автоматически'),
          ),
          const PopupMenuItem(value: 'rename', child: Text('Переименовать')),
          const PopupMenuItem(value: 'address', child: Text('Изменить адрес')),
          const PopupMenuItem(
            value: 'remove',
            child: Text('Удалить устройство'),
          ),
        ],
      ),
    );
  }

  Widget _offer(Map<Object?, Object?> offer) {
    final id = offer['id'] as String;
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              offer['name'].toString(),
              style: Theme.of(context).textTheme.titleMedium,
            ),
            Text(
              '${offer['device']} · ${_size(offer['size'])} · ${offer['seconds']} с',
            ),
            Row(
              children: [
                TextButton(
                  onPressed: () => _run('decide', {'id': id, 'accept': false}),
                  child: const Text('Отклонить'),
                ),
                const SizedBox(width: 8),
                FilledButton(
                  onPressed: () => _run('decide', {'id': id, 'accept': true}),
                  child: const Text('Принять'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _history(Map<Object?, Object?> item) {
    final received = item['direction'] == 'received';
    final uri = item['uri'] as String? ?? '';
    final name = item['name'].toString();
    return ListTile(
      leading: Icon(received ? Icons.download_outlined : Icons.upload_outlined),
      title: Text(name, maxLines: 2, overflow: TextOverflow.ellipsis),
      subtitle: Text(
        '${received ? 'Получено' : 'Отправлено'} · ${_size(item['size'])}',
      ),
      onTap: uri.isEmpty
          ? null
          : () => _run('open', {'uri': uri, 'name': name}),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ready = _state['ready'] == true;
    final limit = _state['limit'] as int? ?? 2048;
    final peers = _items('peers');
    final incoming = _items('incoming');
    final history = _items('history');
    final sendStatus = _state['sendStatus'] as String? ?? '';
    final receiveStatus = _state['receiveStatus'] as String? ?? '';
    final sharedCount = _state['sharedCount'] as int? ?? 0;
    final canSend = peers.isNotEmpty && _state['sending'] != true;
    final networks = _items('networks');
    final found = _items('discovered');
    final searching = _searchEnds?.isAfter(DateTime.now()) ?? false;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Обмен файлами'),
        actions: [
          IconButton(
            tooltip: 'Лимит приёма',
            onPressed: _limit,
            icon: const Icon(Icons.settings_outlined),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 6, 16, 24),
        children: [
          if (networks.isNotEmpty)
            DropdownButtonFormField<String>(
              key: ValueKey(_state['network']),
              initialValue: _state['network'] as String? ?? '',
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Локальная сеть'),
              items: [
                for (final network in networks)
                  DropdownMenuItem(
                    value: network['id'] as String,
                    child: Text(
                      network['name'].toString(),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
              ],
              onChanged: (id) {
                if (id == null) return;
                setState(
                  () => _searchEnds = DateTime.now().add(
                    const Duration(seconds: 6),
                  ),
                );
                unawaited(_run('network', {'network': id}));
              },
            ),
          Card(
            child: SwitchListTile(
              value: ready,
              onChanged: (enabled) => _run('ready', {'enabled': enabled}),
              title: const Text('Готов принимать'),
              subtitle: Text(
                limit == 0
                    ? 'Размер без ограничения'
                    : 'Лимит $limit МиБ на файл',
              ),
            ),
          ),
          if (ready && _state['notifications'] == false)
            const ListTile(
              leading: Icon(Icons.notifications_off_outlined),
              title: Text('Разрешите уведомления в настройках Android'),
              subtitle: Text(
                'Они нужны для подтверждения при свёрнутом приложении.',
              ),
            ),
          const SizedBox(height: 16),
          if (sharedCount > 0)
            Card(
              child: ListTile(
                leading: const Icon(Icons.share_outlined),
                title: Text('Файлов к отправке: $sharedCount'),
                subtitle: peers.isEmpty
                    ? const Text('Сначала сопрягите компьютер.')
                    : null,
                trailing: IconButton(
                  tooltip: 'Убрать файлы',
                  onPressed: () => _run('clearShared'),
                  icon: const Icon(Icons.close),
                ),
              ),
            ),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              FilledButton.icon(
                onPressed: canSend
                    ? () => _chooseReceiver(shared: sharedCount > 0)
                    : null,
                icon: const Icon(Icons.upload_file_outlined),
                label: Text(
                  sharedCount > 0
                      ? 'Отправить выбранное на ПК'
                      : 'Отправить файл на ПК',
                ),
              ),
              OutlinedButton.icon(
                onPressed: _pairing ? null : _scan,
                icon: const Icon(Icons.qr_code_scanner),
                label: const Text('Сканировать QR'),
              ),
              OutlinedButton.icon(
                onPressed: _pairing ? null : _findComputers,
                icon: const Icon(Icons.search),
                label: const Text('Искать в сети'),
              ),
              OutlinedButton(
                onPressed: _pairing ? null : _paste,
                child: const Text('Ввести код'),
              ),
            ],
          ),
          if (_pairing)
            const ListTile(
              leading: SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
              title: Text('Подтвердите подключение в окне на ПК'),
            ),
          if (_showDiscovery) ...[
            const SizedBox(height: 12),
            if (found.isEmpty)
              ListTile(
                title: Text(
                  searching
                      ? 'Ищем компьютеры…'
                      : 'Нет ПК, готовых к сопряжению',
                ),
                subtitle: const Text('На ПК откройте «Подключить телефон».'),
              )
            else
              for (final device in found)
                ListTile(
                  leading: const Icon(Icons.computer_outlined),
                  title: Text(device['name'].toString()),
                  subtitle: Text(device['host'].toString()),
                  trailing: TextButton(
                    onPressed: _pairing ? null : () => _pairFound(device),
                    child: const Text('Подключить'),
                  ),
                ),
          ],
          if (incoming.isNotEmpty) ...[
            const SizedBox(height: 18),
            Text(
              'Входящие файлы',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            ...incoming.map(_offer),
          ],
          const SizedBox(height: 18),
          Text('Компьютеры', style: Theme.of(context).textTheme.titleMedium),
          if (peers.isEmpty)
            const ListTile(
              title: Text('Откройте код подключения в приложении на ПК.'),
            )
          else
            ...peers.map(_device),
          if (sendStatus.isNotEmpty) ListTile(title: Text(sendStatus)),
          if (receiveStatus.isNotEmpty) ListTile(title: Text(receiveStatus)),
          if (history.isNotEmpty) ...[
            const Divider(),
            Text('История', style: Theme.of(context).textTheme.titleMedium),
            ...history.map(_history),
          ],
        ],
      ),
    );
  }
}

class _QrScreen extends StatefulWidget {
  const _QrScreen();

  @override
  State<_QrScreen> createState() => _QrScreenState();
}

class _QrScreenState extends State<_QrScreen> {
  bool _finished = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('QR с экрана ПК')),
      body: MobileScanner(
        onDetect: (capture) {
          if (_finished) return;
          for (final barcode in capture.barcodes) {
            final code = barcode.rawValue;
            if (code != null &&
                code.startsWith('{') &&
                code.contains('"pin"')) {
              _finished = true;
              Navigator.pop(context, code);
              return;
            }
          }
        },
      ),
    );
  }
}
