import 'package:flutter/material.dart';

import '../widgets/common.dart';
import 'club_screen.dart';
import 'roster_screen.dart';
import 'scoring_screen.dart';
import 'sync_screen.dart';

/// Super-admin hub: links to every management tool.
class ManageScreen extends StatelessWidget {
  const ManageScreen({super.key});

  @override
  Widget build(BuildContext context) {
    void go(Widget w) =>
        Navigator.of(context).push(MaterialPageRoute(builder: (_) => w));
    return Scaffold(
      appBar: const LeagueAppBar(title: 'Manage'),
      body: ListView(
        padding: const EdgeInsets.symmetric(vertical: 8),
        children: [
          Card(
            child: ListTile(
              leading: const Icon(
                Icons.scoreboard,
                semanticLabel: 'Scoring entry',
              ),
              title: const Text('Scoring entry'),
              subtitle: const Text('Add score events and corrections'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => go(const ScoringScreen(standalone: true)),
            ),
          ),
          Card(
            child: ListTile(
              leading: const Icon(
                Icons.groups,
                semanticLabel: 'Roster management',
              ),
              title: const Text('Roster management'),
              subtitle: const Text('Transfer, loan or release players'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => go(const RosterScreen()),
            ),
          ),
          Card(
            child: ListTile(
              leading: const Icon(Icons.shield, semanticLabel: 'Clubs'),
              title: const Text('Clubs'),
              subtitle: const Text('Club profiles, staff and rosters'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => go(const ClubsScreen()),
            ),
          ),
          Card(
            child: ListTile(
              leading: const Icon(Icons.sync, semanticLabel: 'Sync queue'),
              title: const Text('Sync queue'),
              subtitle: const Text('Pending offline actions and results'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => go(const SyncScreen()),
            ),
          ),
        ],
      ),
    );
  }
}
