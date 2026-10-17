import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/app_state.dart';
import 'fixtures_screen.dart';
import 'manage_screen.dart';
import 'profile_screen.dart';
import 'roster_screen.dart';
import 'scoring_screen.dart';
import 'standings_screen.dart';
import 'store_screen.dart';

class _Tab {
  final String label;
  final IconData icon;
  final IconData selectedIcon;
  final Widget page;
  const _Tab(this.label, this.icon, this.selectedIcon, this.page);
}

/// Role-aware home with bottom navigation.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  List<_Tab> _tabs(AppUser user) => [
    const _Tab('Fixtures', Icons.event_outlined, Icons.event, FixturesScreen()),
    const _Tab(
      'Standings',
      Icons.leaderboard_outlined,
      Icons.leaderboard,
      StandingsScreen(),
    ),
    const _Tab(
      'Store',
      Icons.storefront_outlined,
      Icons.storefront,
      StoreScreen(),
    ),
    if (user.role == Roles.superAdmin)
      const _Tab(
        'Manage',
        Icons.admin_panel_settings_outlined,
        Icons.admin_panel_settings,
        ManageScreen(),
      )
    else if (user.role == Roles.organizer)
      const _Tab(
        'Scoring',
        Icons.scoreboard_outlined,
        Icons.scoreboard,
        ScoringScreen(),
      )
    else if (user.role == Roles.manager)
      const _Tab('Roster', Icons.groups_outlined, Icons.groups, RosterScreen()),
    const _Tab('Profile', Icons.person_outline, Icons.person, ProfileScreen()),
  ];

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final tabs = _tabs(app.user!);
    if (_index >= tabs.length) _index = 0;
    return PopScope(
      canPop: _index == 0,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) setState(() => _index = 0);
      },
      child: Scaffold(
        body: IndexedStack(
          index: _index,
          children: tabs.map((t) => t.page).toList(),
        ),
        bottomNavigationBar: NavigationBar(
          selectedIndex: _index,
          onDestinationSelected: (i) => setState(() => _index = i),
          labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
          destinations: [
            for (final t in tabs)
              NavigationDestination(
                icon: Icon(t.icon),
                selectedIcon: Icon(t.selectedIcon),
                label: t.label,
                tooltip: t.label,
              ),
          ],
        ),
      ),
    );
  }
}
