import 'dart:async';

import 'package:flutter/foundation.dart';

import 'api_client.dart';

enum NetStatus { online, offline, syncing }

/// Detects online/offline by pinging GET /api/v1/ping periodically, and by
/// observing the outcome of every API call.
class ConnectivityService extends ChangeNotifier {
  final ApiClient api;
  final Duration interval;
  Timer? _timer;
  bool _online = false;
  bool _syncing = false;
  bool _checked = false;
  int _timeouts = 0;

  /// Fired when the app goes from offline to online.
  VoidCallback? onBackOnline;

  ConnectivityService(this.api, {this.interval = const Duration(seconds: 5)}) {
    api.onReachability = _report;
  }

  bool get isOnline => _online;
  bool get hasChecked => _checked;
  NetStatus get status => _syncing
      ? NetStatus.syncing
      : (_online ? NetStatus.online : NetStatus.offline);

  set syncing(bool v) {
    if (_syncing == v) return;
    _syncing = v;
    notifyListeners();
  }

  void start() {
    _timer?.cancel();
    _timer = Timer.periodic(interval, (_) => check());
    check();
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
  }

  Future<bool> check() async {
    try {
      await api.get(
        '/api/v1/ping',
        auth: false,
        timeout: const Duration(seconds: 4),
      );
      _timeouts = 0;
      _report(true);
    } on ApiException catch (e) {
      if (e.code == 'TIMEOUT') {
        // Two slow pings in a row (or no answer yet at all) mean offline.
        _timeouts++;
        if (_timeouts >= 2 || !_checked) _report(false);
      } else {
        _timeouts = 0;
        // A 429 (rate limit) still proves the server is reachable.
        _report(!e.isNetwork);
      }
    } catch (_) {
      _report(false);
    }
    return _online;
  }

  void _report(bool reachable) {
    final wasOnline = _online;
    final first = !_checked;
    _checked = true;
    if (reachable == _online && !first) return;
    _online = reachable;
    notifyListeners();
    if (reachable && (!wasOnline || first)) onBackOnline?.call();
  }

  @override
  void dispose() {
    stop();
    super.dispose();
  }
}
