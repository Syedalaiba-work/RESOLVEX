import 'package:flutter/material.dart';

import '../models/models.dart';
import '../screens/sync_screen.dart';
import '../services/app_state.dart';
import '../services/connectivity_service.dart';

/// Always-visible Online / Offline / Syncing indicator for app bars.
/// Tapping it opens the pending-action queue.
class SyncStatusChip extends StatelessWidget {
  const SyncStatusChip({super.key});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.read(context);
    return ListenableBuilder(
      listenable: Listenable.merge([app.connectivity, app.sync]),
      builder: (context, _) {
        final status = app.connectivity.status;
        final pending = app.sync.pending.length;
        late final IconData icon;
        late final String text;
        late final Color bg;
        switch (status) {
          case NetStatus.online:
            icon = Icons.cloud_done;
            text = 'Online';
            bg = const Color(0xFF1B5E20);
          case NetStatus.offline:
            icon = Icons.cloud_off;
            text = 'Offline';
            bg = const Color(0xFFB71C1C);
          case NetStatus.syncing:
            icon = Icons.sync;
            text = 'Syncing';
            bg = const Color(0xFF0D47A1);
        }
        final label = pending > 0 ? '$text · $pending pending' : text;
        return Semantics(
          button: true,
          label: 'Connection status: $label. Tap to open the sync queue.',
          excludeSemantics: true,
          child: InkWell(
            borderRadius: BorderRadius.circular(24),
            onTap: () => Navigator.of(context)
                .push(MaterialPageRoute(builder: (_) => const SyncScreen())),
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: 48, minWidth: 48),
              child: Center(
                child: Container(
                  margin: const EdgeInsets.symmetric(horizontal: 6),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 6,
                  ),
                  decoration: BoxDecoration(
                    color: bg,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: Colors.white70),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(icon, size: 16, color: Colors.white),
                      const SizedBox(width: 4),
                      Text(
                        pending > 0 ? '$text ($pending)' : text,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

/// Standard app bar with tenant logo badge and the sync status chip.
class LeagueAppBar extends StatelessWidget implements PreferredSizeWidget {
  final String title;
  final List<Widget> actions;
  final PreferredSizeWidget? bottom;
  const LeagueAppBar({
    super.key,
    required this.title,
    this.actions = const [],
    this.bottom,
  });

  @override
  Size get preferredSize =>
      Size.fromHeight(kToolbarHeight + (bottom?.preferredSize.height ?? 0));

  @override
  Widget build(BuildContext context) {
    final canPop = Navigator.of(context).canPop();
    return AppBar(
      title: Row(
        children: [
          if (!canPop) ...[const LogoBadge(), const SizedBox(width: 8)],
          Expanded(child: Text(title, overflow: TextOverflow.ellipsis)),
        ],
      ),
      actions: [...actions, const SyncStatusChip(), const SizedBox(width: 4)],
      bottom: bottom,
    );
  }
}

class LogoBadge extends StatelessWidget {
  final double size;
  const LogoBadge({super.key, this.size = 32});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final text =
        app.tenant?.logoText ??
        (app.user?.role == Roles.superAdmin ? 'NA' : 'NL');
    final scheme = Theme.of(context).colorScheme;
    return Semantics(
      label: '${app.tenant?.name ?? 'NaSCon League'} logo',
      excludeSemantics: true,
      child: Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: scheme.secondary,
          shape: BoxShape.circle,
        ),
        child: FittedBox(
          child: Padding(
            padding: const EdgeInsets.all(4),
            child: Text(
              text,
              style: TextStyle(
                color: scheme.onSecondary,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class LoadingView extends StatelessWidget {
  final String message;
  const LoadingView({super.key, this.message = 'Loading...'});

  @override
  Widget build(BuildContext context) => Center(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const CircularProgressIndicator(),
        const SizedBox(height: 12),
        Text(message),
      ],
    ),
  );
}

class MessageView extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? message;
  final String? actionLabel;
  final VoidCallback? onAction;
  const MessageView({
    super.key,
    required this.icon,
    required this.title,
    this.message,
    this.actionLabel,
    this.onAction,
  });

  @override
  Widget build(BuildContext context) => Center(
    child: SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            icon,
            size: 56,
            color: Theme.of(context).colorScheme.primary,
            semanticLabel: title,
          ),
          const SizedBox(height: 12),
          Text(
            title,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleMedium,
          ),
          if (message != null) ...[
            const SizedBox(height: 8),
            Text(message!, textAlign: TextAlign.center),
          ],
          if (onAction != null) ...[
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: onAction,
              icon: const Icon(Icons.refresh),
              label: Text(actionLabel ?? 'Try again'),
            ),
          ],
        ],
      ),
    ),
  );
}

class ErrorView extends StatelessWidget {
  final String message;
  final VoidCallback? onRetry;
  const ErrorView({super.key, required this.message, this.onRetry});

  @override
  Widget build(BuildContext context) => MessageView(
    icon: Icons.error_outline,
    title: 'Could not load this page',
    message: message,
    actionLabel: 'Try again',
    onAction: onRetry,
  );
}

class EmptyView extends StatelessWidget {
  final String title;
  final String? message;
  final IconData icon;
  const EmptyView({
    super.key,
    required this.title,
    this.message,
    this.icon = Icons.inbox_outlined,
  });

  @override
  Widget build(BuildContext context) =>
      MessageView(icon: icon, title: title, message: message);
}

/// Banner shown above content that came from the offline cache.
class CachedBanner extends StatelessWidget {
  final DateTime? savedAt;
  const CachedBanner({super.key, this.savedAt});

  @override
  Widget build(BuildContext context) {
    final when = savedAt == null
        ? ''
        : ' (saved ${friendlyTime(savedAt!.toUtc().toIso8601String())})';
    return Material(
      color: const Color(0xFFFFF3E0),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: Row(
          children: [
            const Icon(
              Icons.cloud_off,
              color: Color(0xFFE65100),
              semanticLabel: 'Offline',
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                'Offline: showing saved data$when.',
                style: const TextStyle(
                  color: Color(0xFF4E342E),
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Banner listing queued actions waiting to be synced.
class PendingBanner extends StatelessWidget {
  final String? type;
  const PendingBanner({super.key, this.type});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.read(context);
    return ListenableBuilder(
      listenable: app.sync,
      builder: (context, _) {
        final items = app.sync.pending
            .where((a) => type == null || a.type == type)
            .toList();
        if (items.isEmpty) return const SizedBox.shrink();
        return Material(
          color: const Color(0xFFE3F2FD),
          child: InkWell(
            onTap: () => Navigator.of(context)
                .push(MaterialPageRoute(builder: (_) => const SyncScreen())),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              child: Row(
                children: [
                  const Icon(
                    Icons.schedule,
                    color: Color(0xFF0D47A1),
                    semanticLabel: 'Pending',
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      '${items.length} pending action${items.length == 1 ? '' : 's'} waiting to sync. Tap to view.',
                      style: const TextStyle(
                        color: Color(0xFF0D47A1),
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class MatchStatusBadge extends StatelessWidget {
  final String status;
  const MatchStatusBadge({super.key, required this.status});

  @override
  Widget build(BuildContext context) {
    late final IconData icon;
    late final Color color;
    switch (status) {
      case 'in_progress':
        icon = Icons.fiber_manual_record;
        color = const Color(0xFFC62828);
      case 'completed':
        icon = Icons.check_circle;
        color = const Color(0xFF424242);
      default:
        icon = Icons.schedule;
        color = const Color(0xFF1565C0);
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        border: Border.all(color: color),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 4),
          Text(
            statusLabel(status),
            style: TextStyle(
              color: color,
              fontWeight: FontWeight.bold,
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }
}

class QualificationBadge extends StatelessWidget {
  final String status;
  const QualificationBadge({super.key, required this.status});

  static (IconData, String, Color) info(String status) {
    switch (status) {
      case 'clinched':
        return (Icons.verified, 'Qualified', const Color(0xFF1B5E20));
      case 'eliminated':
        return (Icons.cancel, 'Eliminated', const Color(0xFFB71C1C));
      default:
        return (Icons.help_outline, 'Still possible', const Color(0xFF37474F));
    }
  }

  @override
  Widget build(BuildContext context) {
    final (icon, text, color) = info(status);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 16, color: color),
        const SizedBox(width: 4),
        Text(
          text,
          style: TextStyle(
            color: color,
            fontWeight: FontWeight.w600,
            fontSize: 12,
          ),
        ),
      ],
    );
  }
}

Future<bool> confirm(
  BuildContext context, {
  required String title,
  required String message,
  String confirmLabel = 'Confirm',
}) async {
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: SingleChildScrollView(child: Text(message)),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx, false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(ctx, true),
          child: Text(confirmLabel),
        ),
      ],
    ),
  );
  return ok ?? false;
}

void showSuccess(BuildContext context, String message) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Row(
          children: [
            const Icon(
              Icons.check_circle,
              color: Colors.white,
              semanticLabel: 'Success',
            ),
            const SizedBox(width: 8),
            Expanded(child: Text(message)),
          ],
        ),
        backgroundColor: const Color(0xFF2E7D32),
      ),
    );
}

void showInfo(BuildContext context, String message) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(message)));
}

void showError(BuildContext context, String message) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Row(
          children: [
            const Icon(
              Icons.error_outline,
              color: Colors.white,
              semanticLabel: 'Error',
            ),
            const SizedBox(width: 8),
            Expanded(child: Text(message)),
          ],
        ),
        backgroundColor: const Color(0xFFB71C1C),
        duration: const Duration(seconds: 6),
      ),
    );
}
