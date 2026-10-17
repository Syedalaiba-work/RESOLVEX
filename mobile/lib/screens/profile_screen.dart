import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/app_state.dart';
import '../widgets/common.dart';
import 'club_screen.dart';
import 'settings_screen.dart';
import 'sync_screen.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final u = app.user!;
    final scheme = Theme.of(context).colorScheme;
    void go(Widget w) =>
        Navigator.of(context).push(MaterialPageRoute(builder: (_) => w));
    return Scaffold(
      appBar: const LeagueAppBar(title: 'Profile'),
      body: ListView(
        children: [
          Container(
            color: scheme.primary,
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                const LogoBadge(size: 56),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        u.displayName,
                        style: TextStyle(
                          color: scheme.onPrimary,
                          fontSize: 20,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      Text(u.email, style: TextStyle(color: scheme.onPrimary)),
                      const SizedBox(height: 4),
                      Text(
                        '${Roles.label(u.role)}${app.tenant != null ? ' · ${app.tenant!.name}' : ''}',
                        style: TextStyle(
                          color: scheme.onPrimary,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          if (u.clubId != null)
            ListTile(
              leading: const Icon(Icons.shield, semanticLabel: 'My club'),
              title: const Text('My club'),
              subtitle: Text(u.clubId!),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => go(ClubScreen(clubId: u.clubId!, title: 'My club')),
            ),
          ListTile(
            leading: const Icon(Icons.groups_2, semanticLabel: 'Clubs'),
            title: const Text('All clubs'),
            subtitle: const Text('Club info, roster, staff and venue'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => go(const ClubsScreen()),
          ),
          ListTile(
            leading: const Icon(Icons.sync, semanticLabel: 'Sync queue'),
            title: const Text('Sync status and pending actions'),
            subtitle: ListenableBuilder(
              listenable: app.sync,
              builder: (_, _) => Text('${app.sync.pending.length} pending'),
            ),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => go(const SyncScreen()),
          ),
          ListTile(
            leading: const Icon(Icons.dns, semanticLabel: 'Server settings'),
            title: const Text('Server settings'),
            subtitle: Text(app.serverUrl),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => go(const SettingsScreen()),
          ),
          const Divider(),
          ListTile(
            leading: Icon(
              Icons.logout,
              color: scheme.error,
              semanticLabel: 'Sign out',
            ),
            title: Text('Sign out', style: TextStyle(color: scheme.error)),
            onTap: () async {
              final pending = app.sync.pending.length;
              final ok = await confirm(
                context,
                title: 'Sign out?',
                message: pending > 0
                    ? 'You have $pending pending action(s). They stay on this phone and will sync after you sign in again.'
                    : 'You will need to sign in again to use the app.',
                confirmLabel: 'Sign out',
              );
              if (ok) await app.logout();
            },
          ),
        ],
      ),
    );
  }
}
