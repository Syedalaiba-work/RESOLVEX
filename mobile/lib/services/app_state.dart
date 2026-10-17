import 'dart:convert';

import 'package:flutter/widgets.dart';
import 'package:http/http.dart' as http;

import '../models/models.dart';
import 'api_client.dart';
import 'connectivity_service.dart';
import 'local_store.dart';
import 'repository.dart';
import 'sync_service.dart';
import 'token_store.dart';

const String kDefaultServer = 'http://10.0.2.2:8080';

/// Application-wide state: session, server address, cart, and the services.
class AppState extends ChangeNotifier {
  final TokenStore tokens;
  final LocalStore store;
  late final ApiClient api;
  late final Repository repo;
  late final ConnectivityService connectivity;
  late final SyncService sync;

  String serverUrl = kDefaultServer;
  String? _token;
  AppUser? user;
  Tenant? tenant;
  bool ready = false;
  String? sessionNotice;
  final List<CartLine> cart = [];

  AppState({
    required http.Client client,
    required this.tokens,
    required this.store,
    Duration? pingInterval,
  }) {
    api = ApiClient(client, baseUrl: () => serverUrl, token: () => _token);
    repo = Repository(api, store);
    connectivity = ConnectivityService(
      api,
      interval: pingInterval ?? const Duration(seconds: 5),
    );
    sync = SyncService(api, store, connectivity);
    connectivity.onBackOnline = _autoSync;
    api.onUnauthorized = () {
      if (_token != null) {
        sessionNotice = 'Your session has ended. Please sign in again.';
        logout();
      }
    };
  }

  bool get loggedIn => _token != null && user != null;
  int get cartCount => cart.fold(0, (s, l) => s + l.quantity);
  int get cartTotal => cart.fold(0, (s, l) => s + l.totalMinor);

  Future<void> init() async {
    serverUrl = await store.getSetting('server_url') ?? kDefaultServer;
    var device = await store.getSetting('device_id');
    if (device == null) {
      device = randomId('dev');
      await store.setSetting('device_id', device);
    }
    sync.deviceId = device;
    _token = await tokens.read('token');
    final u = await tokens.read('user');
    final t = await tokens.read('tenant');
    if (_token != null && u != null) {
      try {
        user = AppUser.fromJson(
          Map<String, dynamic>.from(jsonDecode(u) as Map),
        );
        if (t != null && t != 'null') {
          tenant = Tenant.fromJson(
            Map<String, dynamic>.from(jsonDecode(t) as Map),
          );
        }
      } catch (_) {
        _token = null;
        user = null;
      }
    } else {
      _token = null;
    }
    await sync.load();
    ready = true;
    notifyListeners();
    connectivity.start();
  }

  Future<void> setServerUrl(String url) async {
    var u = url.trim();
    if (u.isNotEmpty && !u.startsWith('http://') && !u.startsWith('https://')) {
      u = 'http://$u';
    }
    if (u.endsWith('/')) u = u.substring(0, u.length - 1);
    serverUrl = u.isEmpty ? kDefaultServer : u;
    await store.setSetting('server_url', serverUrl);
    notifyListeners();
    connectivity.check();
  }

  Future<void> login(String email, String password) async {
    final res = await api.post('/api/v1/auth/login', {
      'email': email.trim(),
      'password': password,
    }, auth: false);
    final m = res is Map ? Map<String, dynamic>.from(res) : <String, dynamic>{};
    final token = m['token']?.toString();
    if (token == null || token.isEmpty || m['user'] is! Map) {
      throw ApiException(
        'UNAUTHENTICATED',
        message: 'The server gave an unexpected answer. Please try again.',
      );
    }
    _token = token;
    user = AppUser.fromJson(Map<String, dynamic>.from(m['user'] as Map));
    tenant = m['tenant'] is Map
        ? Tenant.fromJson(Map<String, dynamic>.from(m['tenant'] as Map))
        : null;
    sessionNotice = null;
    await tokens.write('token', token);
    await tokens.write('user', jsonEncode(user!.toJson()));
    await tokens.write('tenant', jsonEncode(tenant?.toJson()));
    notifyListeners();
    _autoSync();
  }

  Future<void> logout() async {
    _token = null;
    user = null;
    tenant = null;
    cart.clear();
    await tokens.delete('token');
    await tokens.delete('user');
    await tokens.delete('tenant');
    notifyListeners();
  }

  DateTime? _lastWarm;

  void _autoSync() {
    if (!loggedIn) return;
    if (sync.pending.isNotEmpty) sync.syncNow();
    final now = DateTime.now();
    if (_lastWarm == null ||
        now.difference(_lastWarm!) > const Duration(minutes: 2)) {
      _lastWarm = now;
      repo.warmCache(roster: user?.canManageRoster ?? false);
    }
  }

  // ---- Cart ----
  void addToCart(Product p, Variant v, int qty) {
    final existing = cart.where((l) => l.variant.variantId == v.variantId);
    if (existing.isNotEmpty) {
      existing.first.quantity = (existing.first.quantity + qty).clamp(1, 10);
    } else {
      cart.add(CartLine(product: p, variant: v, quantity: qty.clamp(1, 10)));
    }
    notifyListeners();
  }

  void setQuantity(CartLine line, int qty) {
    if (qty <= 0) {
      cart.remove(line);
    } else {
      line.quantity = qty.clamp(1, 10);
    }
    notifyListeners();
  }

  void clearCart() {
    cart.clear();
    notifyListeners();
  }

  @override
  void dispose() {
    connectivity.dispose();
    sync.dispose();
    super.dispose();
  }
}

/// Makes [AppState] available to the widget tree.
class AppScope extends InheritedNotifier<AppState> {
  const AppScope({super.key, required AppState state, required super.child})
    : super(notifier: state);

  static AppState of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<AppScope>()!.notifier!;

  static AppState read(BuildContext context) =>
      context.getInheritedWidgetOfExactType<AppScope>()!.notifier!;
}
