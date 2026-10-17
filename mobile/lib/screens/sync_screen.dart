import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/app_state.dart';
import '../services/connectivity_service.dart';
import '../services/sync_service.dart';
import '../widgets/common.dart';

/// Sync status: connection state, pending-action queue, last sync results.
class SyncScreen extends StatelessWidget {
  const SyncScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.read(context);
    return Scaffold(
      appBar: const LeagueAppBar(title: 'Sync status'),
      body: ListenableBuilder(
        listenable: Listenable.merge([app.sync, app.connectivity]),
        builder: (context, _) {
          final s = app.sync;
          final status = app.connectivity.status;
          final statusText = switch (status) {
            NetStatus.online => 'Online - connected to the server',
            NetStatus.offline => 'Offline - actions are saved on this phone',
            NetStatus.syncing => 'Syncing - sending your saved actions',
          };
          return ListView(
            padding: const EdgeInsets.all(12),
            children: [
              Card(
                margin: EdgeInsets.zero,
                child: ListTile(
                  leading: Icon(switch (status) {
                    NetStatus.online => Icons.cloud_done,
                    NetStatus.offline => Icons.cloud_off,
                    NetStatus.syncing => Icons.sync,
                  }, semanticLabel: statusText),
                  title: Text(
                    statusText,
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                  subtitle: Text(
                    s.lastSyncAt == null
                        ? 'Not synced yet'
                        : 'Last sync: ${friendlyTime(s.lastSyncAt)}',
                  ),
                ),
              ),
              const SizedBox(height: 12),
              FilledButton.icon(
                key: const Key('sync_now'),
                style: FilledButton.styleFrom(
                  minimumSize: const Size.fromHeight(52),
                ),
                onPressed: (s.busy || s.pending.isEmpty)
                    ? null
                    : () async {
                        final online = await app.connectivity.check();
                        if (!context.mounted) return;
                        if (!online) {
                          showError(
                            context,
                            'Still offline. Your actions are kept and will sync when you are back online.',
                          );
                          return;
                        }
                        final results = await app.sync.syncNow();
                        if (!context.mounted) return;
                        if (results.isNotEmpty) {
                          final applied = results
                              .where((r) => r.status != 'rejected')
                              .length;
                          final rejected = results.length - applied;
                          if (rejected == 0) {
                            showSuccess(
                              context,
                              'Sync complete: $applied action(s) saved.',
                            );
                          } else {
                            showInfo(
                              context,
                              'Sync complete: $applied saved, $rejected not saved. See the reasons below.',
                            );
                          }
                        }
                      },
                icon: s.busy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.sync),
                label: Text(
                  s.pending.isEmpty
                      ? 'Nothing to sync'
                      : 'Sync now (${s.pending.length})',
                ),
              ),
              if (s.lastError != null) ...[
                const SizedBox(height: 8),
                Text(
                  s.lastError!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              const SizedBox(height: 16),
              Text(
                'Pending actions (${s.pending.length})',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              if (s.pending.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(12),
                  child: Text(
                    'No pending actions. Anything you do while offline will wait here.',
                  ),
                ),
              for (final a in s.pending)
                Card(
                  margin: const EdgeInsets.symmetric(vertical: 4),
                  child: ListTile(
                    leading: Icon(
                      a.type == 'score_event'
                          ? Icons.scoreboard
                          : Icons.swap_horiz,
                      semanticLabel: a.type == 'score_event'
                          ? 'Score action'
                          : 'Roster action',
                    ),
                    title: Text(a.label.isEmpty ? a.type : a.label),
                    subtitle: Text(
                      'Pending · saved ${friendlyTime(a.queuedAt)}',
                    ),
                    trailing: IconButton(
                      tooltip: 'Discard this action',
                      icon: const Icon(Icons.delete_outline),
                      onPressed: () async {
                        final ok = await confirm(
                          context,
                          title: 'Discard action?',
                          message:
                              '"${a.label}" will be removed and never sent to the server.',
                          confirmLabel: 'Discard',
                        );
                        if (ok) await app.sync.discard(a.actionId);
                      },
                    ),
                  ),
                ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'Last sync results',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                  ),
                  if (s.lastResults.isNotEmpty)
                    TextButton(
                      onPressed: () => app.sync.clearResults(),
                      child: const Text('Clear'),
                    ),
                ],
              ),
              if (s.lastResults.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(12),
                  child: Text('No results yet.'),
                ),
              for (final r in s.lastResults) _ResultTile(result: r),
            ],
          );
        },
      ),
    );
  }
}

class _ResultTile extends StatelessWidget {
  final SyncResult result;
  const _ResultTile({required this.result});

  @override
  Widget build(BuildContext context) {
    final r = result;
    final (icon, word, color) = switch (r.status) {
      'applied' => (Icons.check_circle, 'Applied', const Color(0xFF1B5E20)),
      'duplicate' => (
        Icons.copy_all,
        'Already applied',
        const Color(0xFF37474F),
      ),
      _ => (Icons.cancel, 'Rejected', const Color(0xFFB71C1C)),
    };
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4),
      child: ListTile(
        leading: Icon(icon, color: color, semanticLabel: word),
        title: Text(r.label.isEmpty ? r.actionId : r.label),
        subtitle: Text('$word. ${describeSyncResult(r)}'),
      ),
    );
  }
}
