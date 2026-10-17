import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/actions.dart';
import '../services/api_client.dart';
import '../services/app_state.dart';
import '../services/repository.dart';
import '../services/sync_service.dart';
import '../widgets/common.dart';
import '../widgets/loader.dart';

const Map<String, List<String>> kDefaultEventTypes = {
  'football': ['goal'],
  'basketball': ['free_throw', 'two_pointer', 'three_pointer'],
  'cricket': ['run', 'four', 'six', 'wicket', 'wide', 'no_ball', 'dot'],
  'esports': ['round_win'],
};

/// League Organizer: append score events and compensating events.
class ScoringScreen extends StatefulWidget {
  final String? initialMatchId;
  final bool standalone;
  const ScoringScreen({
    super.key,
    this.initialMatchId,
    this.standalone = false,
  });

  @override
  State<ScoringScreen> createState() => _ScoringScreenState();
}

class _ScoringScreenState extends State<ScoringScreen> {
  String? _matchId;
  int _reload = 0;

  @override
  void initState() {
    super.initState();
    _matchId = widget.initialMatchId;
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.read(context);
    return Scaffold(
      appBar: const LeagueAppBar(title: 'Scoring entry'),
      body: Column(
        children: [
          const PendingBanner(type: 'score_event'),
          Expanded(
            child: Loader<List<Fixture>>(
              loadingMessage: 'Loading matches...',
              load: () => app.repo.fixtures(),
              builder: (context, fixtures, refresh) {
                if (fixtures.isEmpty) {
                  return const EmptyView(
                    icon: Icons.event_busy,
                    title: 'No matches yet',
                    message: 'There are no matches you can score.',
                  );
                }
                final sorted = [...fixtures]
                  ..sort((a, b) {
                    int rank(String s) =>
                        s == 'in_progress' ? 0 : (s == 'upcoming' ? 1 : 2);
                    return rank(a.status).compareTo(rank(b.status));
                  });
                final selected = sorted.any((f) => f.matchId == _matchId)
                    ? _matchId!
                    : sorted.first.matchId;
                return Column(
                  children: [
                    Padding(
                      padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
                      child: DropdownButtonFormField<String>(
                        key: ValueKey('match-$selected'),
                        initialValue: selected,
                        isExpanded: true,
                        decoration: const InputDecoration(
                          labelText: 'Match',
                          prefixIcon: Icon(Icons.sports),
                        ),
                        items: sorted
                            .map(
                              (f) => DropdownMenuItem(
                                value: f.matchId,
                                child: Text(
                                  '${statusLabel(f.status)}: ${f.homeName} vs ${f.awayName}',
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                            )
                            .toList(),
                        onChanged: (v) => setState(() => _matchId = v),
                      ),
                    ),
                    Expanded(
                      child: Loader<MatchDetail>(
                        key: ValueKey('detail-$selected-$_reload'),
                        reloadKey: '$selected-$_reload',
                        loadingMessage: 'Loading match...',
                        load: () => _loadMatch(
                          app,
                          sorted.firstWhere((f) => f.matchId == selected),
                        ),
                        builder: (context, m, refresh) => _ScoringForm(
                          match: m,
                          onChanged: () => setState(() => _reload++),
                        ),
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

/// Loads the match; when offline and never opened before, falls back to the
/// cached fixture (base_version 0 = "device saw nothing", the server rebases).
Future<Loaded<MatchDetail>> _loadMatch(AppState app, Fixture f) async {
  try {
    return await app.repo.match(f.matchId);
  } on ApiException catch (e) {
    if (!e.isNetwork) rethrow;
    return Loaded(
      MatchDetail(
        matchId: f.matchId,
        sportId: f.sportId,
        leagueId: f.leagueId,
        status: f.status,
        outcome: 'pending',
        home: TeamScore(teamId: f.homeTeamId, score: f.homeScore ?? 0),
        away: TeamScore(teamId: f.awayTeamId, score: f.awayScore ?? 0),
        homeName: f.homeName,
        awayName: f.awayName,
        scheduledAt: f.scheduledAt,
        version: 0,
        events: const [],
      ),
      fromCache: true,
    );
  }
}

class _ScoringForm extends StatefulWidget {
  final MatchDetail match;
  final VoidCallback onChanged;
  const _ScoringForm({required this.match, required this.onChanged});

  @override
  State<_ScoringForm> createState() => _ScoringFormState();
}

class _ScoringFormState extends State<_ScoringForm> {
  late String _teamId;
  late String _eventType;
  bool _busy = false;

  List<String> get _types {
    final m = widget.match;
    final set = <String>{...?kDefaultEventTypes[m.sportId]};
    for (final e in m.events) {
      if (e.type == 'score' && e.payload['event_type'] != null) {
        set.add(e.payload['event_type'].toString());
      }
    }
    if (set.isEmpty) set.add('goal');
    return set.toList();
  }

  @override
  void initState() {
    super.initState();
    _teamId = widget.match.home.teamId;
    _eventType = _types.first;
  }

  Future<void> _submit(
    Map<String, dynamic> body,
    String label,
    String successText,
  ) async {
    final app = AppScope.read(context);
    setState(() => _busy = true);
    try {
      final outcome = await performOrQueue(
        app,
        type: 'score_event',
        baseVersion: widget.match.version,
        payload: body,
        label: label,
        online: () => app.repo.postEvent(body),
      );
      if (!mounted) return;
      if (outcome == ActionOutcome.queued) {
        showInfo(
          context,
          'You are offline. "$label" is saved as pending and will sync automatically.',
        );
      } else {
        showSuccess(context, successText);
        widget.onChanged();
      }
    } on ApiException catch (e) {
      if (mounted) showError(context, e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _appendScore() async {
    final m = widget.match;
    final label =
        '${_pretty(_eventType)} for ${m.nameFor(_teamId)} (${m.homeName} vs ${m.awayName})';
    await _submit(
      {
        'event_id': randomId('evt'),
        'match_id': m.matchId,
        'type': 'score',
        'payload': {'team_id': _teamId, 'event_type': _eventType},
      },
      label,
      'Recorded: ${_pretty(_eventType)} for ${m.nameFor(_teamId)}.',
    );
  }

  Future<void> _compensate(MatchEvent e) async {
    final m = widget.match;
    final reasonCtl = TextEditingController(text: 'Scoring correction');
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cancel this event?'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'A correcting event will cancel "${_describe(m, e)}". The original stays in the log.',
              ),
              const SizedBox(height: 12),
              TextField(
                controller: reasonCtl,
                decoration: const InputDecoration(labelText: 'Reason'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Keep event'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Cancel event'),
          ),
        ],
      ),
    );
    final reason = reasonCtl.text.trim().isEmpty
        ? 'Scoring correction'
        : reasonCtl.text.trim();
    reasonCtl.dispose();
    if (ok != true || !mounted) return;
    await _submit(
      {
        'event_id': randomId('evt'),
        'match_id': m.matchId,
        'type': 'compensation',
        'payload': {'compensates': e.eventId, 'reason': reason},
      },
      'Correction of "${_describe(m, e)}"',
      'Correction recorded. The event no longer counts.',
    );
  }

  String _pretty(String s) =>
      s.isEmpty ? s : s[0].toUpperCase() + s.substring(1).replaceAll('_', ' ');

  String _describe(MatchDetail m, MatchEvent e) {
    if (e.type == 'score') {
      return '${_pretty(e.payload['event_type']?.toString() ?? 'score')} - ${m.nameFor(e.payload['team_id']?.toString() ?? '')} (#${e.sequence})';
    }
    return '${_pretty(e.type)} #${e.sequence}';
  }

  @override
  Widget build(BuildContext context) {
    final m = widget.match;
    final live = m.status == 'in_progress';
    final correctable = m.events
        .where((e) => e.compensatable)
        .toList()
        .reversed
        .toList();
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        Card(
          margin: EdgeInsets.zero,
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              children: [
                MatchStatusBadge(status: m.status),
                const SizedBox(height: 8),
                Text(
                  '${m.homeName}  ${m.home.score} - ${m.away.score}  ${m.awayName}',
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                Text(
                  'Version ${m.version}',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
        ),
        if (!live)
          const Padding(
            padding: EdgeInsets.only(top: 8),
            child: Text(
              'Note: score events can only be added while a match is LIVE. '
              'Corrections are allowed at any time.',
            ),
          ),
        const SizedBox(height: 16),
        Text(
          'Add a score event',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 8),
        SegmentedButton<String>(
          segments: [
            ButtonSegment(
              value: m.home.teamId,
              label: Text(m.homeName, overflow: TextOverflow.ellipsis),
            ),
            ButtonSegment(
              value: m.away.teamId,
              label: Text(m.awayName, overflow: TextOverflow.ellipsis),
            ),
          ],
          selected: {_teamId},
          onSelectionChanged: (s) => setState(() => _teamId = s.first),
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          initialValue: _eventType,
          decoration: const InputDecoration(labelText: 'Event type'),
          items: _types
              .map((t) => DropdownMenuItem(value: t, child: Text(_pretty(t))))
              .toList(),
          onChanged: (v) => setState(() => _eventType = v ?? _eventType),
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          key: const Key('add_score'),
          onPressed: _busy ? null : _appendScore,
          icon: _busy
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.add_circle),
          label: Text(
            'Add ${_pretty(_eventType)} for ${m.nameFor(_teamId)}',
            overflow: TextOverflow.ellipsis,
          ),
        ),
        const SizedBox(height: 20),
        Text(
          'Correct an earlier event',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        if (correctable.isEmpty)
          const Padding(
            padding: EdgeInsets.all(12),
            child: Text('No events that can be corrected yet.'),
          ),
        for (final e in correctable)
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.history, semanticLabel: 'Event'),
            title: Text(_describe(m, e)),
            trailing: OutlinedButton(
              onPressed: _busy ? null : () => _compensate(e),
              child: const Text('Correct'),
            ),
          ),
      ],
    );
  }
}
