import '../models/models.dart';
import 'api_client.dart';
import 'local_store.dart';

/// Result of a read: either fresh from the server or from the local cache.
class Loaded<T> {
  final T data;
  final bool fromCache;
  final DateTime? savedAt;
  const Loaded(this.data, {this.fromCache = false, this.savedAt});
}

/// Read-side data access with an offline cache (network first, cache fallback).
class Repository {
  final ApiClient api;
  final LocalStore store;
  Repository(this.api, this.store);

  Future<Loaded<T>> _cached<T>(
    String key,
    String path,
    T Function(dynamic json) parse,
  ) async {
    try {
      final json = await api.get(path);
      await store.putCache(key, json);
      return Loaded(parse(json));
    } on ApiException catch (e) {
      if (e.isNetwork || (e.status != null && e.status! >= 500)) {
        final c = await store.getCache(key);
        if (c != null) {
          return Loaded(parse(c.data), fromCache: true, savedAt: c.savedAt);
        }
      }
      rethrow;
    }
  }

  static List<Map<String, dynamic>> _list(dynamic j) {
    if (j is List) {
      return j
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
    }
    if (j is Map) {
      for (final k in const ['items', 'results', 'data']) {
        if (j[k] is List) return _list(j[k]);
      }
    }
    return const [];
  }

  static Map<String, dynamic> _map(dynamic j) =>
      j is Map ? Map<String, dynamic>.from(j) : {};

  Future<Loaded<List<League>>> leagues() => _cached(
    'leagues',
    '/api/v1/leagues',
    (j) => _list(j).map(League.fromJson).toList(),
  );

  Future<Loaded<List<Fixture>>> fixtures() => _cached(
    'fixtures',
    '/api/v1/fixtures',
    (j) => _list(j).map(Fixture.fromJson).toList(),
  );

  Future<Loaded<MatchDetail>> match(String id) => _cached(
    'match:$id',
    '/api/v1/matches/${Uri.encodeComponent(id)}',
    (j) => MatchDetail.fromJson(_map(j)),
  );

  Future<Loaded<Standings>> standings(String leagueId) => _cached(
    'standings:$leagueId',
    '/api/v1/standings/${Uri.encodeComponent(leagueId)}',
    (j) => Standings.fromJson(_map(j)),
  );

  Future<Loaded<List<ClubSummary>>> clubs() => _cached(
    'clubs',
    '/api/v1/clubs',
    (j) => _list(j).map(ClubSummary.fromJson).toList(),
  );

  Future<Loaded<ClubProfile>> club(String id) => _cached(
    'club:$id',
    '/api/v1/clubs/${Uri.encodeComponent(id)}',
    (j) => ClubProfile.fromJson(_map(j)),
  );

  Future<Loaded<List<Product>>> products() => _cached(
    'products',
    '/api/v1/products',
    (j) => _list(j).map(Product.fromJson).toList(),
  );

  Future<Loaded<RosterView>> roster(String leagueId) => _cached(
    'roster:$leagueId',
    '/api/v1/roster/${Uri.encodeComponent(leagueId)}',
    (j) => RosterView.fromJson(_map(j)),
  );

  /// Saves the screens a judge/user is likely to open offline into the cache.
  Future<void> warmCache({bool roster = false}) async {
    Future<void> safe(Future<void> Function() f) async {
      try {
        await f();
      } catch (_) {}
    }

    await safe(() async {
      final f = await fixtures();
      if (f.fromCache) return;
      for (final m in f.data.where((x) => x.status == 'in_progress')) {
        await safe(() => match(m.matchId));
      }
    });
    await safe(() async {
      final l = await leagues();
      if (l.fromCache) return;
      for (final x in l.data) {
        await safe(() => standings(x.leagueId));
      }
    });
    await safe(() async {
      final c = await clubs();
      if (c.fromCache) return;
      for (final x in c.data) {
        await safe(() => club(x.clubId));
      }
    });
    await safe(() => products());
    if (roster) await safe(() => this.roster('league-alpha-1'));
  }

  Future<CheckoutResult> checkout(Map<String, dynamic> body) async =>
      CheckoutResult.fromJson(_map(await api.post('/api/v1/checkout', body)));

  Future<Map<String, dynamic>> postEvent(Map<String, dynamic> body) async =>
      _map(await api.post('/api/v1/events', body));

  Future<Map<String, dynamic>> postTransfer(Map<String, dynamic> body) async =>
      _map(await api.post('/api/v1/roster/transfer', body));
}
