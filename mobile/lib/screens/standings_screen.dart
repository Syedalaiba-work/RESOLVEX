import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/app_state.dart';
import '../widgets/common.dart';
import '../widgets/loader.dart';
import 'club_screen.dart';

class StandingsScreen extends StatefulWidget {
  const StandingsScreen({super.key});

  @override
  State<StandingsScreen> createState() => _StandingsScreenState();
}

class _StandingsScreenState extends State<StandingsScreen> {
  String? _leagueId;

  @override
  Widget build(BuildContext context) {
    final app = AppScope.read(context);
    return Scaffold(
      appBar: const LeagueAppBar(title: 'Standings'),
      body: Loader<List<League>>(
        loadingMessage: 'Loading leagues...',
        load: () => app.repo.leagues(),
        builder: (context, leagues, refresh) {
          if (leagues.isEmpty) {
            return const EmptyView(
              icon: Icons.leaderboard,
              art: SportArt.basketball,
              title: 'No leagues yet',
              message: 'Standings appear once a league has been created.',
            );
          }
          final preferred = app.user?.leagueId;
          final selected =
              _leagueId ??
              (leagues.any((l) => l.leagueId == 'league-alpha-1')
                  ? 'league-alpha-1'
                  : (leagues.any((l) => l.leagueId == preferred)
                        ? preferred!
                        : leagues.first.leagueId));
          return Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
                child: DropdownButtonFormField<String>(
                  initialValue: selected,
                  isExpanded: true,
                  decoration: const InputDecoration(
                    labelText: 'League',
                    prefixIcon: Icon(Icons.emoji_events_outlined),
                  ),
                  items: leagues
                      .map(
                        (l) => DropdownMenuItem(
                          value: l.leagueId,
                          child: Text(l.name, overflow: TextOverflow.ellipsis),
                        ),
                      )
                      .toList(),
                  onChanged: (v) => setState(() => _leagueId = v),
                ),
              ),
              Expanded(
                child: Loader<Standings>(
                  key: ValueKey(selected),
                  reloadKey: selected,
                  loadingMessage: 'Loading standings...',
                  load: () => app.repo.standings(selected),
                  builder: (context, s, refresh) => RefreshIndicator(
                    onRefresh: refresh,
                    child: StandingsTable(s),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class StandingsTable extends StatelessWidget {
  final Standings standings;
  const StandingsTable(this.standings, {super.key});

  @override
  Widget build(BuildContext context) {
    final s = standings;
    if (s.table.isEmpty) {
      return ListView(
        children: const [
          SizedBox(
            height: 360,
            child: EmptyView(
              icon: Icons.leaderboard,
              title: 'No results yet',
              message: 'The table fills in after the first match is completed.',
            ),
          ),
        ],
      );
    }
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.only(bottom: 16),
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
          child: Text(
            'Top ${s.qualificationSpots} qualify. P = played, W-D-L = won-drawn-lost, GD = difference, Pts = points.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ),
        for (final r in s.table) _row(context, s, r),
      ],
    );
  }

  Widget _row(BuildContext context, Standings s, StandingRow r) {
    final name = s.nameFor(r.teamId);
    final (_, statusText, _) = QualificationBadge.info(r.status);
    final diff = r.diff is double
        ? (r.diff as double).toStringAsFixed(3)
        : r.diff.toString();
    return Card(
      child: Semantics(
        button: true,
        label:
            'Rank ${r.rank}, $name, ${r.points} points, played ${r.played}, '
            'won ${r.won}, drawn ${r.drawn}, lost ${r.lost}, difference $diff. $statusText. Open club.',
        excludeSemantics: true,
        child: InkWell(
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => ClubScreen(clubId: r.teamId, title: name),
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 18,
                  backgroundColor: Theme.of(context).colorScheme.primary,
                  foregroundColor: Theme.of(context).colorScheme.onPrimary,
                  child: Text(
                    '${r.rank}',
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        'P ${r.played} · W-D-L ${r.won}-${r.drawn}-${r.lost} · GD $diff',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                      const SizedBox(height: 4),
                      QualificationBadge(status: r.status),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                Column(
                  children: [
                    Text(
                      '${r.points}',
                      style: TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.w800,
                        color: Theme.of(context).colorScheme.primary,
                      ),
                    ),
                    const Text('Pts', style: TextStyle(fontSize: 12)),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
