import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';

import '../models/models.dart';
import 'api_client.dart';
import 'connectivity_service.dart';
import 'error_messages.dart';
import 'local_store.dart';

String randomId(String prefix) {
  final r = Random.secure();
  final hex = List.generate(12, (_) => r.nextInt(16).toRadixString(16)).join();
  return '$prefix-${DateTime.now().millisecondsSinceEpoch.toRadixString(36)}-$hex';
}

/// Plain-language explanation for one sync result.
String describeSyncResult(SyncResult r) {
  switch (r.status) {
    case 'applied':
      return r.resolution == 'rebased_append'
          ? 'Saved. Others had made changes in the meantime; yours was added on top.'
          : 'Saved on the server.';
    case 'duplicate':
      return 'Already saved earlier, nothing changed.';
    case 'rejected':
      return 'Not saved: ${friendlyError(r.errorCode)}';
  }
  return 'Unknown result.';
}

/// Owns the persistent offline action queue and replays it via POST /api/v1/sync.
class SyncService extends ChangeNotifier {
  final ApiClient api;
  final LocalStore store;
  final ConnectivityService connectivity;

  List<QueuedAction> _pending = [];
  List<SyncResult> _lastResults = [];
  String? _lastError;
  String? _lastSyncAt;
  bool _busy = false;
  String deviceId = 'device';

  SyncService(this.api, this.store, this.connectivity);

  List<QueuedAction> get pending => List.unmodifiable(_pending);
  List<SyncResult> get lastResults => List.unmodifiable(_lastResults);
  String? get lastError => _lastError;
  String? get lastSyncAt => _lastSyncAt;
  bool get busy => _busy;

  Future<void> load() async {
    _pending = await store.pendingActions();
    final raw = await store.getSetting('last_sync_results');
    if (raw != null) {
      try {
        final j = jsonDecode(raw) as Map;
        _lastSyncAt = j['at'] as String?;
        _lastResults = (j['results'] as List)
            .map(
              (e) => SyncResult.fromJson(Map<String, dynamic>.from(e as Map)),
            )
            .toList();
      } catch (_) {}
    }
    notifyListeners();
  }

  Future<QueuedAction> enqueue({
    required String type,
    required int baseVersion,
    required Map<String, dynamic> payload,
    required String label,
  }) async {
    final action = QueuedAction(
      actionId: randomId('act'),
      type: type,
      queuedAt: utcStamp(),
      baseVersion: baseVersion,
      payload: payload,
      label: label,
    );
    await store.enqueue(action);
    _pending = await store.pendingActions();
    notifyListeners();
    return action;
  }

  Future<void> discard(String actionId) async {
    await store.removeActions([actionId]);
    _pending = await store.pendingActions();
    notifyListeners();
  }

  Future<void> clearResults() async {
    _lastResults = [];
    _lastError = null;
    await store.setSetting(
      'last_sync_results',
      jsonEncode({'at': null, 'results': []}),
    );
    notifyListeners();
  }

  /// Sends every queued action. Returns the results (empty if nothing was sent).
  Future<List<SyncResult>> syncNow() async {
    if (_busy) return const [];
    _pending = await store.pendingActions();
    if (_pending.isEmpty) {
      notifyListeners();
      return const [];
    }
    _busy = true;
    _lastError = null;
    connectivity.syncing = true;
    notifyListeners();
    try {
      final batch = _pending.take(100).toList();
      final labels = {for (final a in batch) a.actionId: a.label};
      final res = await api.post('/api/v1/sync', {
        'device_id': deviceId,
        'actions': batch.map((a) => a.toJson()).toList(),
      });
      final list = (res is Map && res['results'] is List)
          ? res['results'] as List
          : const [];
      final results = list.whereType<Map>().map((e) {
        final m = Map<String, dynamic>.from(e);
        m['label'] = labels[m['action_id']] ?? '';
        return SyncResult.fromJson(m);
      }).toList();
      // The server answered for the whole batch: clear it from the queue.
      await store.removeActions(batch.map((a) => a.actionId));
      _pending = await store.pendingActions();
      _lastResults = results;
      _lastSyncAt = utcStamp();
      await store.setSetting(
        'last_sync_results',
        jsonEncode({
          'at': _lastSyncAt,
          'results': results.map((r) => r.toJson()).toList(),
        }),
      );
      return results;
    } on ApiException catch (e) {
      _lastError = e.isNetwork
          ? 'Could not sync because the server is unreachable. Your actions are kept and will be sent later.'
          : 'Sync failed: ${e.message} Your actions are kept.';
      return const [];
    } finally {
      _busy = false;
      connectivity.syncing = false;
      notifyListeners();
    }
  }
}
