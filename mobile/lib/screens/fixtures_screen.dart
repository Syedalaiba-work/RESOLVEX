import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/api_client.dart';
import '../services/app_state.dart';
import '../services/repository.dart';
import '../widgets/common.dart';
import '../widgets/loader.dart';
import 'match_screen.dart';

class FixturesData {
  final List<Fixture> fixtures;
  final Map<String, String> leagueNames;
  const FixturesData(this.fixtures, this.leagueNames);
}

Future<Loaded<FixturesData>> loadFixtures(AppState app) async {
  final f = await app.repo.fixtures();
  Map<String, String> names = {};
  try {
    final l = await app.repo.leagues();
    names = {for (final x in l.data) x.leagueId: x.name};
  } on ApiException {
    // League names are optional decoration.
  }
  return Loaded(
    FixturesData(f.data, names),
    fromCache: f.fromCache,
    savedAt: f.savedAt,
  );
}

class FixturesScreen extends StatefulWidget {
  const FixturesScreen({super.key});

  @override
  State<FixturesScreen> createState() => _FixturesScreenState();
}

class _FixturesScreenState extends State<FixturesScreen> {
  String? _league;

  @override
  Widget build(BuildContext context) {
    final app = AppScope.read(context);
    return Scaffold(
      appBar: const LeagueAppBar(title: 'Fixtures'),
      body: Loader<FixturesData>(
        loadingMessage: 'Loading fixtures...',
        load: () => loadFixtures(app),
        builder: (context, data, refresh) {
          final leagues = <String>{
            for (final f in data.fixtures)
              if (f.leagueId != null) f.leagueId!,
          }.toList()..sort();
          final shown =
              data.fixtures
                  .where((f) => _league == null || f.leagueId == _league)
                  .toList()
                ..sort((a, b) {
                  int rank(String s) =>
                      s == 'in_progress' ? 0 : (s == 'upcoming' ? 1 : 2);
                  final r = rank(a.status).compareTo(rank(b.status));
                  if (r != 0) return r;
                  return (a.scheduledAt ?? '').compareTo(b.scheduledAt ?? '');
                });
          return RefreshIndicator(
            onRefresh: refresh,
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.only(bottom: 16),
              children: [
                if (leagues.length > 1)
                  SizedBox(
                    height: 56,
                    child: ListView(
                      scrollDirection: Axis.horizontal,
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 4,
                      ),
                      children: [
                        Padding(
                          padding: const EdgeInsets.only(right: 8),
                          child: ChoiceChip(
                            label: const Text('All leagues'),
                            selected: _league == null,
                            onSelected: (_) => setState(() => _league = null),
                          ),
                        ),
                        for (final l in leagues)
                          Padding(
                            padding: const EdgeInsets.only(right: 8),
                            child: ChoiceChip(
                              label: Text(data.leagueNames[l] ?? l),
                              selected: _league == l,
                              onSelected: (_) => setState(() => _league = l),
                            ),
                          ),
                      ],
                    ),
                  ),
                if (shown.isEmpty)
                  const SizedBox(
                    height: 400,
                    child: EmptyView(
                      icon: Icons.event_busy,
                      title: 'No matches yet',
                      message: 'Fixtures will appear here once the league schedule is published.',
                    ),
                  ),
                for (final f in shown)
                  FixtureCard(
                    fixture: f,
                    leagueName: data.leagueNames[f.leagueId],
                  ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class FixtureCard extends StatelessWidget {
  final Fixture fixture;
  final String? leagueName;
  const FixtureCard({super.key, required this.fixture, this.leagueName});

  @override
  Widget build(BuildContext context) {
    final f = fixture;
    final hasScore =
        f.status != 'upcoming' && f.homeScore != null && f.awayScore != null;
    final scoreText = hasScore ? '${f.homeScore} - ${f.awayScore}' : 'vs';
    return Card(
      child: Semantics(
        button: true,
        label:
            '${f.homeName} versus ${f.awayName}, ${statusLabel(f.status)}'
            '${hasScore ? ', score ${f.homeScore} to ${f.awayScore}' : ''}, ${friendlyTime(f.scheduledAt)}. Open match.',
        excludeSemantics: true,
        child: InkWell(
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => MatchScreen(
                matchId: f.matchId,
                title: '${f.homeName} vs ${f.awayName}',
              ),
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    MatchStatusBadge(status: f.status),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        friendlyTime(f.scheduledAt),
                        textAlign: TextAlign.end,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        f.homeName,
                        textAlign: TextAlign.end,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      child: Text(
                        scoreText,
                        style: TextStyle(
                          fontSize: hasScore ? 22 : 16,
                          fontWeight: FontWeight.bold,
                          color: Theme.of(context).colorScheme.primary,
                        ),
                      ),
                    ),
                    Expanded(
                      child: Text(
                        f.awayName,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ),
                if (leagueName != null) ...[
                  const SizedBox(height: 6),
                  Text(
                    leagueName!,
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
