import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// A tiny in-memory fake of the /api/v1 contract for tests.
class FakeBackend {
  bool online = true;
  final List<http.Request> requests = [];
  String role = 'league_organizer';
  List<Map<String, dynamic>> syncResults = [];

  static const fixtures = [
    {
      'match_id': 'm1',
      'league_id': 'league-alpha-1',
      'sport_id': 'football',
      'home_team_id': 'club-alpha-1',
      'away_team_id': 'club-alpha-2',
      'home_name': 'Alpha United',
      'away_name': 'Alpha Rovers',
      'status': 'in_progress',
      'scheduled_at': '2026-10-17T10:00:00Z',
      'home_score': 1,
      'away_score': 0,
    },
    {
      'match_id': 'm2',
      'league_id': 'league-alpha-1',
      'sport_id': 'football',
      'home_team_id': 'club-alpha-3',
      'away_team_id': 'club-alpha-4',
      'home_name': 'Alpha City',
      'away_name': 'Alpha Athletic With A Very Long Club Name',
      'status': 'upcoming',
      'scheduled_at': '2026-10-18T10:00:00Z',
      'home_score': null,
      'away_score': null,
    },
  ];

  static const standings = {
    'league_id': 'league-alpha-1',
    'sport_id': 'football',
    'qualification_spots': 2,
    'table': [
      {
        'rank': 1,
        'team_id': 'club-alpha-1',
        'played': 3,
        'won': 3,
        'drawn': 0,
        'lost': 0,
        'scored': 7,
        'conceded': 1,
        'diff': 6,
        'points': 9,
        'fair_play': 0,
        'status': 'clinched',
        'resolved_by': null,
      },
      {
        'rank': 2,
        'team_id': 'club-alpha-4',
        'played': 3,
        'won': 0,
        'drawn': 0,
        'lost': 3,
        'scored': 0,
        'conceded': 6,
        'diff': -6,
        'points': 0,
        'fair_play': -2,
        'status': 'eliminated',
        'resolved_by': null,
      },
    ],
    'h2h': {},
    'names': {'club-alpha-1': 'Alpha United', 'club-alpha-4': 'Alpha Athletic'},
  };

  http.Client get client => MockClient(handle);

  Future<http.Response> handle(http.Request req) async {
    requests.add(req);
    if (!online) throw http.ClientException('offline');
    final path = req.url.path;
    http.Response json(Object body, [int status = 200]) => http.Response(
      jsonEncode(body),
      status,
      headers: {'content-type': 'application/json'},
    );
    if (path == '/api/v1/ping') return json({'pong': true});
    if (path == '/api/v1/auth/login') {
      final b = jsonDecode(req.body) as Map;
      if (b['password'] != 'Nascon@26') {
        return json({
          'error': {'code': 'UNAUTHENTICATED', 'message': 'bad', 'details': {}},
        }, 401);
      }
      return json({
        'token': 'tok-123',
        'user': {
          'email': b['email'],
          'role': role,
          'display_name': 'Test User',
          'tenant_id': 'tenant-alpha',
          'league_id': null,
          'club_id': 'club-alpha-1',
          'player_id': null,
        },
        'tenant': {
          'tenant_id': 'tenant-alpha',
          'name': 'Alpha Sports',
          'branding': {
            'primary_color': '#0B3D91',
            'accent_color': '#F2A900',
            'logo_text': 'AS',
          },
        },
      });
    }
    if (req.headers['Authorization'] != 'Bearer tok-123') {
      return json({
        'error': {'code': 'UNAUTHENTICATED', 'message': 'no', 'details': {}},
      }, 401);
    }
    if (path == '/api/v1/fixtures') return json(fixtures);
    if (path == '/api/v1/leagues') {
      return json([
        {
          'league_id': 'league-alpha-1',
          'name': 'Demo League',
          'sport_id': 'football',
          'tenant_id': 'tenant-alpha',
        },
      ]);
    }
    if (path == '/api/v1/standings/league-alpha-1') return json(standings);
    if (path == '/api/v1/products') return json([]);
    if (path == '/api/v1/roster/league-alpha-1') {
      return json({
        'league_id': 'league-alpha-1',
        'transfer_window': {'open': '2026-09-01', 'close': '2026-12-31'},
        'squads': [
          {
            'squad_id': 'sq-alpha-1',
            'club_id': 'club-alpha-1',
            'name': 'Alpha United Squad',
            'players': [
              {
                'player_id': 'p1',
                'name': 'Ali Khan',
                'position': 'gk',
                'role': 'captain',
              },
              {
                'player_id': 'p2',
                'name': 'Bilal Ahmed',
                'position': 'df',
                'role': 'starter',
              },
            ],
          },
          {
            'squad_id': 'sq-alpha-2',
            'club_id': 'club-alpha-2',
            'name': 'Alpha Rovers Squad',
            'players': [],
          },
        ],
      });
    }
    if (path == '/api/v1/matches/m1') {
      return json({
        'match_id': 'm1',
        'sport_id': 'football',
        'league_id': 'league-alpha-1',
        'status': 'in_progress',
        'outcome': 'pending',
        'winner_team_id': null,
        'tiebreak_winner_team_id': null,
        'home': {'team_id': 'club-alpha-1', 'score': 1, 'fair_play': 0},
        'away': {'team_id': 'club-alpha-2', 'score': 0, 'fair_play': 0},
        'version': 2,
        'scoring_events': ['goal'],
        'events': [
          {
            'sequence': 1,
            'event_id': 'e1',
            'type': 'match_start',
            'payload': {},
            'compensated': false,
          },
          {
            'sequence': 2,
            'event_id': 'e2',
            'type': 'score',
            'payload': {'team_id': 'club-alpha-1', 'event_type': 'goal'},
            'compensated': false,
          },
        ],
        'home_name': 'Alpha United',
        'away_name': 'Alpha Rovers',
        'scheduled_at': '2026-10-17T10:00:00Z',
        'pinned_product': null,
      });
    }
    if (path == '/api/v1/sync') {
      final b = jsonDecode(req.body) as Map;
      final actions = b['actions'] as List;
      return json({
        'device_id': b['device_id'],
        'results': syncResults.isNotEmpty
            ? syncResults
            : [
                for (var i = 0; i < actions.length; i++)
                  {
                    'action_id': (actions[i] as Map)['action_id'],
                    'status': 'applied',
                    'resolution': 'appended',
                    'error_code': null,
                    'processed_order': i + 1,
                    'server_version': 1,
                    'signature': null,
                  },
              ],
        'summary': {'applied': actions.length, 'rejected': 0, 'duplicate': 0},
      });
    }
    return json({
      'error': {'code': 'NOT_FOUND', 'message': 'nf', 'details': {}},
    }, 404);
  }
}
