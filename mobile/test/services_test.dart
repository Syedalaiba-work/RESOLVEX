import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:nascon_league/models/models.dart';
import 'package:nascon_league/services/actions.dart';
import 'package:nascon_league/services/app_state.dart';
import 'package:nascon_league/services/error_messages.dart';
import 'package:nascon_league/services/local_store.dart';
import 'package:nascon_league/services/sync_service.dart';
import 'package:nascon_league/services/token_store.dart';

import 'fake_backend.dart';

void main() {
  group('formats', () {
    test('utcStamp uses YYYY-MM-DDTHH:MM:SSZ', () {
      expect(
        utcStamp(DateTime.utc(2026, 10, 17, 9, 5, 3)),
        '2026-10-17T09:05:03Z',
      );
      expect(
        RegExp(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$').hasMatch(utcStamp()),
        isTrue,
      );
    });

    test('money is formatted from minor units', () {
      expect(formatMoney(450000), 'PKR 4,500.00');
      expect(formatMoney(5), 'PKR 0.05');
    });

    test('error codes become plain language', () {
      expect(friendlyError('SQUAD_FULL'), 'The destination squad is full.');
      expect(friendlyError(null, status: 500), isNot(contains('500')));
      expect(friendlyError('PAYMENT_DECLINED'), contains('declined'));
    });

    test('queued action serialises to exactly the spec 5.14 format', () {
      const a = QueuedAction(
        actionId: 'a1',
        type: 'score_event',
        queuedAt: '2026-10-17T11:00:00Z',
        baseVersion: 3,
        payload: {
          'event_id': 'evt-9',
          'match_id': 'm1',
          'type': 'score',
          'payload': {'team_id': 't1', 'event_type': 'goal'},
        },
        label: 'Goal',
      );
      expect(a.toJson().keys.toList(), [
        'action_id',
        'type',
        'queued_at',
        'base_version',
        'payload',
      ]);
      expect(
        jsonEncode(a.toJson()),
        '{"action_id":"a1","type":"score_event","queued_at":"2026-10-17T11:00:00Z","base_version":3,'
        '"payload":{"event_id":"evt-9","match_id":"m1","type":"score","payload":{"team_id":"t1","event_type":"goal"}}}',
      );
    });
  });

  test('checkout response parses totals and receipt', () {
    final r = CheckoutResult.fromJson({
      'order_id': 'ord-001',
      'status': 'paid',
      'currency': 'PKR',
      'items': [
        {
          'variant_id': 'var-jersey-001-M',
          'quantity': 1,
          'unit_price_minor': 450000,
        },
      ],
      'subtotal_minor': 450000,
      'discount_minor': 45000,
      'total_minor': 405000,
      'receipt': {
        'payload': {'paid_at': '2026-10-17T11:20:05Z'},
        'signature': 'ab',
        'pdf_base64': 'JVBERi0=',
      },
    });
    expect(r.totalMinor, 405000);
    expect(r.pdfBase64, 'JVBERi0=');
    expect(r.paidAt, '2026-10-17T11:20:05Z');
  });

  group('offline flow', () {
    late FakeBackend backend;
    late MemoryLocalStore store;
    late MemoryTokenStore tokens;

    AppState newApp() => AppState(
      client: backend.client,
      tokens: tokens,
      store: store,
      pingInterval: const Duration(hours: 1),
    );

    setUp(() {
      backend = FakeBackend();
      store = MemoryLocalStore();
      tokens = MemoryTokenStore();
    });

    test('repository falls back to the cache when offline', () async {
      final app = newApp();
      await app.init();
      await app.login('organizer@nascon.test', 'Nascon@26');
      final fresh = await app.repo.fixtures();
      expect(fresh.fromCache, isFalse);
      expect(fresh.data, hasLength(2));

      backend.online = false;
      final cached = await app.repo.fixtures();
      expect(cached.fromCache, isTrue);
      expect(cached.data.first.homeName, 'Alpha United');
      app.dispose();
    });

    test('offline actions are queued, survive restart and sync', () async {
      final app = newApp();
      await app.init();
      await app.login('organizer@nascon.test', 'Nascon@26');
      backend.online = false;
      await app.connectivity.check();
      expect(app.connectivity.isOnline, isFalse);

      final body = {
        'event_id': 'evt-1',
        'match_id': 'm1',
        'type': 'score',
        'payload': {'team_id': 'club-alpha-1', 'event_type': 'goal'},
      };
      final outcome = await performOrQueue(
        app,
        type: 'score_event',
        baseVersion: 4,
        payload: body,
        label: 'Goal',
        online: () => app.repo.postEvent(body),
      );
      expect(outcome, ActionOutcome.queued);
      app.dispose();

      // "Force close": a brand new AppState over the same persistent stores.
      final app2 = newApp();
      await app2.init();
      await app2.connectivity.check();
      expect(app2.loggedIn, isTrue);
      expect(app2.sync.pending, hasLength(1));
      final q = app2.sync.pending.first.toJson();
      expect(q['type'], 'score_event');
      expect(q['base_version'], 4);
      expect(q['payload'], body);

      backend.online = true;
      backend.syncResults = [
        {
          'action_id': q['action_id'],
          'status': 'rejected',
          'resolution': 'server_wins',
          'error_code': 'MATCH_NOT_IN_PROGRESS',
          'processed_order': 1,
          'server_version': 4,
          'signature': null,
        },
      ];
      final results = await app2.sync.syncNow();
      expect(results, hasLength(1));
      expect(describeSyncResult(results.first), contains('not live'));
      expect(app2.sync.pending, isEmpty);
      expect(store.queue, isEmpty);

      final syncReq = backend.requests.lastWhere(
        (r) => r.url.path == '/api/v1/sync',
      );
      final sent = jsonDecode(syncReq.body) as Map;
      expect(sent['device_id'], isNotEmpty);
      expect((sent['actions'] as List).first['action_id'], q['action_id']);
      app2.dispose();
    });

    test('sync failure keeps the queue', () async {
      final app = newApp();
      await app.init();
      await app.login('manager@nascon.test', 'Nascon@26');
      await app.sync.enqueue(
        type: 'roster_transfer',
        baseVersion: 0,
        payload: {'request_id': 'r1'},
        label: 'Move',
      );
      backend.online = false;
      final res = await app.sync.syncNow();
      expect(res, isEmpty);
      expect(app.sync.pending, hasLength(1));
      expect(app.sync.lastError, contains('kept'));
      app.dispose();
    });

    test('bad password gives a plain-language error', () async {
      final app = newApp();
      await app.init();
      await expectLater(
        app.login('viewer@nascon.test', 'wrong'),
        throwsA(predicate((e) => e.toString().contains('not correct'))),
      );
      expect(tokens.data['token'], isNull);
      app.dispose();
    });
  });
}
