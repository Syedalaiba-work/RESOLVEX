import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/actions.dart';
import '../services/api_client.dart';
import '../services/app_state.dart';
import '../services/sync_service.dart';
import '../widgets/common.dart';
import '../widgets/loader.dart';

/// Club Manager: transfer / loan / release players.
class RosterScreen extends StatefulWidget {
  const RosterScreen({super.key});

  @override
  State<RosterScreen> createState() => _RosterScreenState();
}

class _RosterScreenState extends State<RosterScreen> {
  String? _league;
  int _reload = 0;
  List<String> _extraLeagues = const [];

  @override
  void initState() {
    super.initState();
    _loadLeagues();
  }

  Future<void> _loadLeagues() async {
    try {
      final l = await AppScope.read(context).repo.leagues();
      if (mounted) {
        setState(() => _extraLeagues = l.data.map((x) => x.leagueId).toList());
      }
    } catch (_) {
      // Optional: the demo roster league is always offered.
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.read(context);
    final options = <String>{
      'league-alpha-1',
      if (app.user?.leagueId != null) app.user!.leagueId!,
      ..._extraLeagues,
    }.toList();
    final league = _league ?? options.first;
    return Scaffold(
      appBar: const LeagueAppBar(title: 'Roster management'),
      body: Column(
        children: [
          const PendingBanner(type: 'roster_transfer'),
          if (options.length > 1)
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
              child: DropdownButtonFormField<String>(
                initialValue: league,
                decoration: const InputDecoration(labelText: 'League'),
                items: options
                    .map((o) => DropdownMenuItem(value: o, child: Text(o)))
                    .toList(),
                onChanged: (v) => setState(() => _league = v),
              ),
            ),
          Expanded(
            child: Loader<RosterView>(
              key: ValueKey('$league-$_reload'),
              reloadKey: '$league-$_reload',
              loadingMessage: 'Loading squads...',
              load: () => app.repo.roster(league),
              builder: (context, r, refresh) => RefreshIndicator(
                onRefresh: refresh,
                child: _body(context, app, r),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _body(BuildContext context, AppState app, RosterView r) {
    final user = app.user!;
    final mine = user.role == Roles.superAdmin
        ? r.squads
        : r.squads.where((s) => s.clubId == user.clubId).toList();
    final others = r.squads.where((s) => !mine.contains(s)).toList();
    return ListView(
      padding: const EdgeInsets.only(bottom: 24),
      children: [
        if (r.windowOpen != null)
          ListTile(
            leading: const Icon(
              Icons.date_range,
              semanticLabel: 'Transfer window',
            ),
            title: Text('Transfer window: ${r.windowOpen} to ${r.windowClose}'),
            subtitle: const Text(
              'Transfers and loans must take effect inside this window. Releases are allowed any day.',
            ),
          ),
        if (mine.isEmpty)
          const SizedBox(
            height: 300,
            child: EmptyView(
              icon: Icons.groups,
              title: 'No squads to manage',
              message: 'Your club has no squad in this league.',
            ),
          ),
        for (final s in mine) ...[
          _squadHeader(context, s, editable: true),
          if (s.players.isEmpty)
            const ListTile(title: Text('No players in this squad yet.')),
          for (final p in s.players)
            ListTile(
              leading: CircleAvatar(
                child: Text(
                  p.position.isEmpty ? '?' : p.position.toUpperCase(),
                ),
              ),
              title: Text(p.name),
              subtitle: Text(p.role.replaceAll('_', ' ')),
              trailing: FilledButton.tonal(
                onPressed: () => _chooseAction(context, app, r, s, p),
                child: const Text('Move'),
              ),
            ),
        ],
        if (others.isNotEmpty) ...[
          const Divider(height: 32),
          for (final s in others) ...[
            _squadHeader(context, s, editable: false),
            for (final p in s.players)
              ListTile(
                dense: true,
                leading: const Icon(
                  Icons.person_outline,
                  semanticLabel: 'Player',
                ),
                title: Text(p.name),
                subtitle: Text(
                  '${p.position.toUpperCase()} · ${p.role.replaceAll('_', ' ')}',
                ),
              ),
          ],
        ],
      ],
    );
  }

  Widget _squadHeader(
    BuildContext context,
    Squad s, {
    required bool editable,
  }) => Padding(
    padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
    child: Row(
      children: [
        Icon(
          editable ? Icons.edit_note : Icons.visibility,
          semanticLabel: editable ? 'Your squad' : 'Other squad',
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            '${s.name} (${s.players.length} players)${editable ? '' : ' - view only'}',
            style: Theme.of(context).textTheme.titleMedium,
          ),
        ),
      ],
    ),
  );

  Future<void> _chooseAction(
    BuildContext context,
    AppState app,
    RosterView r,
    Squad from,
    RosterPlayer p,
  ) async {
    final type = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (ctx) => SafeArea(
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(
                  'What do you want to do with ${p.name}?',
                  style: Theme.of(ctx).textTheme.titleMedium,
                ),
              ),
              ListTile(
                leading: const Icon(
                  Icons.swap_horiz,
                  semanticLabel: 'Transfer',
                ),
                title: const Text('Transfer'),
                subtitle: const Text('Move permanently to another squad'),
                onTap: () => Navigator.pop(ctx, 'transfer'),
              ),
              ListTile(
                leading: const Icon(Icons.schedule_send, semanticLabel: 'Loan'),
                title: const Text('Loan'),
                subtitle: const Text('Lend to another squad until an end date'),
                onTap: () => Navigator.pop(ctx, 'loan'),
              ),
              ListTile(
                leading: const Icon(
                  Icons.person_remove,
                  semanticLabel: 'Release',
                ),
                title: const Text('Release'),
                subtitle: const Text('Remove the player from the league'),
                onTap: () => Navigator.pop(ctx, 'release'),
              ),
            ],
          ),
        ),
      ),
    );
    if (type == null || !context.mounted) return;
    final destinations = r.squads
        .where((s) => s.squadId != from.squadId)
        .toList();
    if (type != 'release' && destinations.isEmpty) {
      showError(
        context,
        'There is no other squad in this league to move the player to.',
      );
      return;
    }
    final form = await showDialog<_MoveForm>(
      context: context,
      builder: (_) =>
          _MoveDialog(type: type, player: p, destinations: destinations),
    );
    if (form == null || !context.mounted) return;
    final destName = form.to == null
        ? ''
        : destinations.firstWhere((d) => d.squadId == form.to).name;
    final summary = switch (type) {
      'transfer' =>
        'Transfer ${p.name} from ${from.name} to $destName, effective ${form.effective}?',
      'loan' =>
        'Loan ${p.name} from ${from.name} to $destName from ${form.effective} until ${form.loanEnd}?',
      _ =>
        'Release ${p.name} from ${from.name} on ${form.effective}? The player will leave the league.',
    };
    final ok = await confirm(
      context,
      title: 'Please confirm',
      message: summary,
      confirmLabel: 'Yes, ${type == 'release' ? 'release' : type}',
    );
    if (!ok || !context.mounted) return;

    final body = {
      'request_id': randomId('req'),
      'league_id': r.leagueId,
      'player_id': p.playerId,
      'type': type,
      'from_squad_id': from.squadId,
      'to_squad_id': type == 'release' ? null : form.to,
      'effective_date': form.effective,
      'loan_end_date': type == 'loan' ? form.loanEnd : null,
      'reason': form.reason,
      'requested_by': app.user!.email,
    };
    final versionKey = 'player_version:${p.playerId}';
    final base =
        int.tryParse(await app.store.getSetting(versionKey) ?? '') ?? 0;
    final label = switch (type) {
      'transfer' => 'Transfer ${p.name} to $destName',
      'loan' => 'Loan ${p.name} to $destName until ${form.loanEnd}',
      _ => 'Release ${p.name}',
    };
    try {
      final outcome = await performOrQueue(
        app,
        type: 'roster_transfer',
        baseVersion: base,
        payload: body,
        label: label,
        online: () async {
          await app.repo.postTransfer(body);
          await app.store.setSetting(versionKey, '${base + 1}');
        },
      );
      if (!context.mounted) return;
      if (outcome == ActionOutcome.queued) {
        showInfo(
          context,
          'You are offline. "$label" is saved as pending and will sync automatically.',
        );
      } else {
        showSuccess(context, 'Done: $label.');
        setState(() => _reload++);
      }
    } on ApiException catch (e) {
      if (context.mounted) showError(context, e.message);
    }
  }
}

class _MoveForm {
  final String? to;
  final String effective;
  final String? loanEnd;
  final String reason;
  const _MoveForm(this.to, this.effective, this.loanEnd, this.reason);
}

class _MoveDialog extends StatefulWidget {
  final String type;
  final RosterPlayer player;
  final List<Squad> destinations;
  const _MoveDialog({
    required this.type,
    required this.player,
    required this.destinations,
  });

  @override
  State<_MoveDialog> createState() => _MoveDialogState();
}

class _MoveDialogState extends State<_MoveDialog> {
  String? _to;
  late DateTime _effective;
  late DateTime _loanEnd;
  final _reason = TextEditingController();
  String? _error;

  @override
  void initState() {
    super.initState();
    _to = widget.destinations.isEmpty
        ? null
        : widget.destinations.first.squadId;
    final now = DateTime.now();
    _effective = DateTime(now.year, now.month, now.day);
    _loanEnd = _effective.add(const Duration(days: 30));
    _reason.text = switch (widget.type) {
      'transfer' => 'Squad rebalancing',
      'loan' => 'Development loan',
      _ => 'Contract ended',
    };
  }

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  Future<void> _pick(bool loanEnd) async {
    final initial = loanEnd ? _loanEnd : _effective;
    final d = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2020),
      lastDate: DateTime(2035),
    );
    if (d != null) setState(() => loanEnd ? _loanEnd = d : _effective = d);
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.type;
    return AlertDialog(
      title: Text(
        '${t[0].toUpperCase()}${t.substring(1)} ${widget.player.name}',
      ),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (t != 'release')
              DropdownButtonFormField<String>(
                initialValue: _to,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'To squad'),
                items: widget.destinations
                    .map(
                      (s) => DropdownMenuItem(
                        value: s.squadId,
                        child: Text(s.name, overflow: TextOverflow.ellipsis),
                      ),
                    )
                    .toList(),
                onChanged: (v) => setState(() => _to = v),
              ),
            const SizedBox(height: 8),
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.event, semanticLabel: 'Date'),
              title: const Text('Effective date'),
              subtitle: Text(isoDate(_effective)),
              onTap: () => _pick(false),
            ),
            if (t == 'loan')
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(
                  Icons.event_available,
                  semanticLabel: 'Loan end date',
                ),
                title: const Text('Loan ends'),
                subtitle: Text(isoDate(_loanEnd)),
                onTap: () => _pick(true),
              ),
            TextField(
              controller: _reason,
              decoration: const InputDecoration(labelText: 'Reason'),
            ),
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () {
            if (t != 'release' && _to == null) {
              setState(() => _error = 'Please choose a destination squad.');
              return;
            }
            if (t == 'loan' && !_loanEnd.isAfter(_effective)) {
              setState(
                () => _error = 'The loan must end after the effective date.',
              );
              return;
            }
            Navigator.pop(
              context,
              _MoveForm(
                t == 'release' ? null : _to,
                isoDate(_effective),
                t == 'loan' ? isoDate(_loanEnd) : null,
                _reason.text.trim().isEmpty
                    ? 'No reason given'
                    : _reason.text.trim(),
              ),
            );
          },
          child: const Text('Continue'),
        ),
      ],
    );
  }
}
