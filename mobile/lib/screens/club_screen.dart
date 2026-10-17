import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/api_client.dart';
import '../services/app_state.dart';
import '../widgets/common.dart';
import '../widgets/loader.dart';

class ClubsScreen extends StatelessWidget {
  const ClubsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.read(context);
    return Scaffold(
      appBar: const LeagueAppBar(title: 'Clubs'),
      body: Loader<List<ClubSummary>>(
        loadingMessage: 'Loading clubs...',
        load: () => app.repo.clubs(),
        builder: (context, clubs, refresh) => RefreshIndicator(
          onRefresh: refresh,
          child: clubs.isEmpty
              ? ListView(
                  children: const [
                    SizedBox(
                      height: 360,
                      child: EmptyView(
                        icon: Icons.shield_outlined,
                        title: 'No clubs yet',
                      ),
                    ),
                  ],
                )
              : ListView.builder(
                  itemCount: clubs.length,
                  itemBuilder: (context, i) => Card(
                    child: ListTile(
                      leading: const Icon(Icons.shield, semanticLabel: 'Club'),
                      title: Text(clubs[i].name),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => ClubScreen(
                            clubId: clubs[i].clubId,
                            title: clubs[i].name,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
        ),
      ),
    );
  }
}

class ClubScreen extends StatelessWidget {
  final String clubId;
  final String title;
  const ClubScreen({super.key, required this.clubId, this.title = 'Club'});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.read(context);
    return Scaffold(
      appBar: LeagueAppBar(title: title),
      body: Loader<ClubProfile>(
        loadingMessage: 'Loading club...',
        load: () async {
          try {
            return await app.repo.club(clubId);
          } on ApiException catch (e) {
            if (e.status == 404) {
              throw ApiException(
                e.code,
                status: 404,
                message: 'There is no club profile for this team yet.',
              );
            }
            rethrow;
          }
        },
        builder: (context, c, refresh) =>
            RefreshIndicator(onRefresh: refresh, child: _body(context, c)),
      ),
    );
  }

  static String _historyLine(dynamic h) {
    if (h is Map) {
      final parts = <String>[
        if (h['season'] != null) 'Season ${h['season']}',
        if (h['position'] != null) 'finished #${h['position']}',
        if (h['points'] != null) '${h['points']} pts',
      ];
      if (parts.isNotEmpty) return parts.join(', ');
      return h.entries.map((e) => '${e.key}: ${e.value}').join(', ');
    }
    return h.toString();
  }

  Widget _section(BuildContext context, String text) => Padding(
    padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
    child: Text(text, style: Theme.of(context).textTheme.titleMedium),
  );

  Widget _body(BuildContext context, ClubProfile c) {
    final scheme = Theme.of(context).colorScheme;
    final history = c.history;
    return ListView(
      padding: const EdgeInsets.only(bottom: 24),
      children: [
        Container(
          color: scheme.primary,
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              CircleAvatar(
                radius: 28,
                backgroundColor: scheme.secondary,
                child: Icon(
                  Icons.shield,
                  color: scheme.onSecondary,
                  size: 30,
                  semanticLabel: 'Club crest',
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  c.name,
                  style: TextStyle(
                    color: scheme.onPrimary,
                    fontSize: 22,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
        ),
        _section(context, 'Club info'),
        ListTile(
          leading: const Icon(Icons.stadium, semanticLabel: 'Home venue'),
          title: const Text('Home venue'),
          subtitle: Text(
            c.homeVenue?.isNotEmpty == true ? c.homeVenue! : 'Not listed',
          ),
        ),
        for (final e in c.social.entries)
          ListTile(
            leading: const Icon(Icons.public, semanticLabel: 'Social link'),
            title: Text(e.key),
            subtitle: Text('${e.value}'),
          ),
        if (history != null &&
            history.toString().isNotEmpty &&
            history.toString() != '[]')
          ListTile(
            leading: const Icon(Icons.history_edu, semanticLabel: 'History'),
            title: const Text('History'),
            subtitle: Text(
              history is List
                  ? history.map(_historyLine).join('\n')
                  : history.toString(),
            ),
          ),
        _section(context, 'Staff'),
        if (c.staff.isEmpty)
          const ListTile(title: Text('No staff listed yet.')),
        for (final s in c.staff)
          ListTile(
            leading: const Icon(Icons.badge, semanticLabel: 'Staff member'),
            title: Text(
              '${s['name'] ?? s['display_name'] ?? s['email'] ?? 'Staff'}',
            ),
            subtitle: Text('${s['role'] ?? s['title'] ?? ''}'),
          ),
        _section(context, 'Roster (${c.roster.length} players)'),
        if (c.roster.isEmpty)
          const ListTile(title: Text('No players registered yet.')),
        for (final p in c.roster)
          ListTile(
            leading: CircleAvatar(
              child: Text(p.position.isEmpty ? '?' : p.position.toUpperCase()),
            ),
            title: Text(p.name),
            subtitle: Text(
              [
                p.role.replaceAll('_', ' '),
                if (p.squadId != null) 'Squad ${p.squadId}',
              ].join(' · '),
            ),
          ),
      ],
    );
  }
}
