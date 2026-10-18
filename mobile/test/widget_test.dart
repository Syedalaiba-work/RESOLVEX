import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nascon_league/main.dart';
import 'package:nascon_league/services/app_state.dart';
import 'package:nascon_league/services/local_store.dart';
import 'package:nascon_league/services/token_store.dart';
import 'package:nascon_league/widgets/common.dart';

import 'fake_backend.dart';

void main() {
  late FakeBackend backend;
  late MemoryLocalStore store;
  late MemoryTokenStore tokens;

  setUp(() {
    backend = FakeBackend();
    store = MemoryLocalStore();
    tokens = MemoryTokenStore();
  });

  Future<AppState> start(
    WidgetTester tester, {
    Size size = const Size(360, 640),
  }) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    final app = AppState(
      client: backend.client,
      tokens: tokens,
      store: store,
      pingInterval: const Duration(hours: 1),
    );
    await app.init();
    await tester.pumpWidget(LeagueApp(state: app));
    await tester.pumpAndSettle();
    return app;
  }

  Future<void> finish(WidgetTester tester, AppState app) async {
    app.connectivity.stop();
    await tester.pumpWidget(const SizedBox());
  }

  Future<void> signIn(WidgetTester tester, String email) async {
    await tester.enterText(find.byKey(const Key('email')), email);
    await tester.enterText(find.byKey(const Key('password')), 'Nascon@26');
    await tester.ensureVisible(find.byKey(const Key('signin')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('signin')));
    await tester.pumpAndSettle();
  }

  testWidgets('organizer signs in and sees fixtures plus the Scoring tab', (
    tester,
  ) async {
    backend.role = 'league_organizer';
    final app = await start(tester);
    expect(find.text('Sign in'), findsWidgets);
    await signIn(tester, 'organizer@nascon.test');

    expect(app.loggedIn, isTrue);
    expect(tokens.data['token'], 'tok-123');
    expect(find.text('Alpha United'), findsWidgets);
    expect(find.text('LIVE'), findsWidgets);
    expect(find.text('Scoring'), findsOneWidget);
    expect(find.text('Roster'), findsNothing);
    expect(find.text('Online'), findsWidgets);
    expect(tester.takeException(), isNull);
    await finish(tester, app);
  });

  testWidgets('viewer has no management tabs', (tester) async {
    backend.role = 'viewer';
    final app = await start(tester);
    await signIn(tester, 'viewer@nascon.test');
    expect(find.text('Fixtures'), findsWidgets);
    expect(find.text('Standings'), findsWidgets);
    expect(find.text('Store'), findsWidgets);
    expect(find.text('Profile'), findsWidgets);
    expect(find.text('Scoring'), findsNothing);
    expect(find.text('Roster'), findsNothing);
    await finish(tester, app);
  });

  testWidgets('manager sees Roster tab; standings show status as text', (
    tester,
  ) async {
    backend.role = 'club_manager';
    final app = await start(tester);
    await signIn(tester, 'manager@nascon.test');
    expect(find.text('Roster'), findsOneWidget);
    await tester.tap(find.text('Standings').last);
    await tester.pumpAndSettle();
    expect(find.text('Qualified'), findsOneWidget);
    expect(find.text('Eliminated'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await finish(tester, app);
  });

  testWidgets(
    'screen readers can activate fixture cards, standings rows and the status chip',
    (tester) async {
      final semantics = tester.ensureSemantics();
      backend.role = 'viewer';
      final app = await start(tester);
      await signIn(tester, 'viewer@nascon.test');

      bool tappable(Finder f) => tester
          .getSemantics(f)
          .getSemanticsData()
          .hasAction(SemanticsAction.tap);

      final chip = find.bySemanticsLabel(RegExp(r'^Connection status'));
      expect(tappable(chip.first), isTrue);
      final card = find.bySemanticsLabel(RegExp(r'versus'));
      expect(card, findsWidgets);
      expect(tappable(card.first), isTrue);

      // Activate the card the way TalkBack does: through the semantics tap action.
      final node = tester.getSemantics(card.first);
      node.owner!.performAction(node.id, SemanticsAction.tap);
      await tester.pumpAndSettle();
      expect(find.text('Match timeline'), findsOneWidget);

      await tester.pageBack();
      await tester.pumpAndSettle();
      await tester.tap(find.text('Standings').last);
      await tester.pumpAndSettle();
      final row = find.bySemanticsLabel(RegExp(r'^Rank 1,'));
      expect(tappable(row), isTrue);

      expect(tester.takeException(), isNull);
      semantics.dispose();
      await finish(tester, app);
    },
  );

  testWidgets('wrong password shows a plain-language error', (tester) async {
    final app = await start(tester);
    await tester.enterText(
      find.byKey(const Key('email')),
      'viewer@nascon.test',
    );
    await tester.enterText(find.byKey(const Key('password')), 'nope');
    await tester.tap(find.byKey(const Key('signin')));
    await tester.pumpAndSettle();
    expect(find.textContaining('not correct'), findsOneWidget);
    expect(find.textContaining('401'), findsNothing);
    await finish(tester, app);
  });

  testWidgets('offline: cached fixtures still open with an Offline indicator', (
    tester,
  ) async {
    backend.role = 'viewer';
    var app = await start(tester);
    await signIn(tester, 'viewer@nascon.test');
    await finish(tester, app);

    // Reopen the app while offline.
    backend.online = false;
    app = await start(tester);
    await tester.pumpAndSettle();
    expect(find.text('Offline'), findsWidgets);
    expect(find.textContaining('Offline: showing saved data'), findsWidgets);
    expect(find.text('Alpha United'), findsWidgets);
    expect(tester.takeException(), isNull);
    await finish(tester, app);
  });

  testWidgets('no overflow in landscape on a small phone', (tester) async {
    backend.role = 'league_organizer';
    final app = await start(tester, size: const Size(640, 360));
    await signIn(tester, 'organizer@nascon.test');
    for (final tab in [
      'Standings',
      'Store',
      'Scoring',
      'Profile',
      'Fixtures',
    ]) {
      await tester.tap(find.text(tab).last);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: 'overflow on $tab');
    }
    await finish(tester, app);
  });

  testWidgets(
    'organizer scores offline: action is queued as pending, then syncs',
    (tester) async {
      backend.role = 'league_organizer';
      final app = await start(tester);
      await signIn(tester, 'organizer@nascon.test');

      backend.online = false;
      await app.connectivity.check();
      await tester.pumpAndSettle();
      await tester.tap(find.text('Scoring').last);
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.byKey(const Key('add_score')));
      await tester.tap(find.byKey(const Key('add_score')));
      await tester.pumpAndSettle();

      expect(app.sync.pending, hasLength(1));
      final a = app.sync.pending.first.toJson();
      expect(a['type'], 'score_event');
      expect(a['base_version'], 2);
      expect((a['payload'] as Map)['type'], 'score');
      expect(store.queue, hasLength(1));
      expect(find.textContaining('1 pending action'), findsOneWidget);
      expect(find.text('Offline (1)'), findsWidgets);

      backend.online = true;
      await app.connectivity.check(); // back online -> automatic sync
      await tester.pumpAndSettle();
      expect(app.sync.pending, isEmpty);
      expect(app.sync.lastResults.single.status, 'applied');
      await finish(tester, app);
    },
  );

  testWidgets(
    'manager transfers a player offline with confirmation; rejection explained after sync',
    (tester) async {
      backend.role = 'club_manager';
      final app = await start(tester);
      await signIn(tester, 'manager@nascon.test');
      await tester.tap(find.text('Roster').last);
      await tester.pumpAndSettle();
      expect(find.text('Bilal Ahmed'), findsOneWidget);

      backend.online = false;
      await app.connectivity.check();
      await tester.pumpAndSettle();

      await tester.tap(find.text('Move').at(1));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Transfer'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();
      expect(find.text('Please confirm'), findsOneWidget);
      await tester.tap(find.text('Yes, transfer'));
      await tester.pumpAndSettle();

      expect(app.sync.pending, hasLength(1));
      final a = app.sync.pending.first.toJson();
      expect(a['type'], 'roster_transfer');
      final p = a['payload'] as Map;
      expect(p['player_id'], 'p2');
      expect(p['from_squad_id'], 'sq-alpha-1');
      expect(p['to_squad_id'], 'sq-alpha-2');
      expect(p['type'], 'transfer');
      expect(p['league_id'], 'league-alpha-1');

      backend.syncResults = [
        {
          'action_id': a['action_id'],
          'status': 'rejected',
          'resolution': 'server_wins',
          'error_code': 'SQUAD_FULL',
          'processed_order': 1,
          'server_version': 0,
          'signature': null,
        },
      ];
      backend.online = true;
      await app.connectivity.check();
      await tester.pumpAndSettle();
      expect(app.sync.pending, isEmpty);

      await tester.tap(find.byType(SyncStatusChip).first);
      await tester.pumpAndSettle();
      expect(
        find.textContaining('The destination squad is full'),
        findsOneWidget,
      );
      await finish(tester, app);
    },
  );
}
