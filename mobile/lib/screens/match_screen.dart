import 'dart:async';

import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/api_client.dart';
import '../services/app_state.dart';
import '../services/repository.dart';
import '../widgets/common.dart';
import 'club_screen.dart';
import 'scoring_screen.dart';
import 'store_screen.dart';

/// Match detail: live score (refreshes every 3 s while visible), event
/// timeline and the pinned product showcase.
class MatchScreen extends StatefulWidget {
  final String matchId;
  final String title;
  const MatchScreen({super.key, required this.matchId, this.title = 'Match'});

  @override
  State<MatchScreen> createState() => _MatchScreenState();
}

class _MatchScreenState extends State<MatchScreen> {
  Loaded<MatchDetail>? _data;
  String? _error;
  Timer? _timer;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 3), (_) {
      if (!mounted) return;
      final route = ModalRoute.of(context);
      if (route == null || route.isCurrent) _load(silent: true);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load({bool silent = false}) async {
    if (_loading) return;
    _loading = true;
    if (!silent) setState(() => _error = null);
    try {
      final d = await AppScope.read(context).repo.match(widget.matchId);
      if (mounted) {
        setState(() {
          _data = d;
          _error = null;
        });
      }
    } on ApiException catch (e) {
      if (mounted && (!silent || _data == null)) {
        setState(
          () => _error = e.isNetwork
              ? 'You are offline and this match has not been saved on this phone yet.'
              : e.message,
        );
      }
    } finally {
      _loading = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final d = _data;
    return Scaffold(
      appBar: LeagueAppBar(title: widget.title),
      floatingActionButton: (d != null && app.user!.canScore)
          ? FloatingActionButton.extended(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => ScoringScreen(
                    initialMatchId: d.data.matchId,
                    standalone: true,
                  ),
                ),
              ),
              icon: const Icon(Icons.scoreboard),
              label: const Text('Score entry'),
            )
          : null,
      body: d == null
          ? (_error != null
                ? ErrorView(message: _error!, onRetry: _load)
                : const LoadingView(message: 'Loading match...'))
          : Column(
              children: [
                if (d.fromCache) CachedBanner(savedAt: d.savedAt),
                Expanded(child: _body(context, d.data)),
              ],
            ),
    );
  }

  Widget _body(BuildContext context, MatchDetail m) {
    final scheme = Theme.of(context).colorScheme;
    final events = m.events.reversed.toList();
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.only(bottom: 88),
        children: [
          // Score header
          Container(
            margin: heroMargin,
            decoration: heroDecoration(),
            padding: const EdgeInsets.fromLTRB(12, 18, 12, 22),
            child: Column(
              children: [
                // Wrap, not Row: on a 360 dp phone with large text the hint moves to a second line
                // instead of overflowing.
                Wrap(
                  alignment: WrapAlignment.center,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  runSpacing: 6,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: MatchStatusBadge(status: m.status),
                    ),
                    if (m.status == 'in_progress') ...[
                      const SizedBox(width: 8),
                      Text(
                        'Updates every 3 s',
                        style: TextStyle(color: scheme.onPrimary, fontSize: 12),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 12),
                Semantics(
                  label:
                      'Score: ${m.homeName} ${m.home.score}, ${m.awayName} ${m.away.score}',
                  excludeSemantics: true,
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: _team(
                          context,
                          m.homeName,
                          m.home,
                          m.home.teamId,
                        ),
                      ),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 8),
                        child: AnimatedScore(
                          '${m.home.score} - ${m.away.score}',
                          key: const Key('live_score'),
                          style: const TextStyle(
                            fontSize: 44,
                            fontWeight: FontWeight.w900,
                            letterSpacing: -1,
                            color: AppColors.lime,
                          ),
                        ),
                      ),
                      Expanded(
                        child: _team(
                          context,
                          m.awayName,
                          m.away,
                          m.away.teamId,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  _outcome(m),
                  style: TextStyle(
                    color: scheme.onPrimary,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                Text(
                  friendlyTime(m.scheduledAt),
                  style: TextStyle(
                    color: scheme.onPrimary.withValues(alpha: 0.85),
                  ),
                ),
              ],
            ),
          ),
          if (m.pinnedProduct != null) _pinned(context, m.pinnedProduct!),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
            child: Text(
              'Match timeline',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
          if (events.isEmpty)
            const Padding(
              padding: EdgeInsets.all(24),
              child: Text(
                'No events yet. They will appear here as the match goes on.',
                textAlign: TextAlign.center,
              ),
            ),
          for (final e in events) _eventTile(context, m, e),
        ],
      ),
    );
  }

  String _outcome(MatchDetail m) {
    switch (m.outcome) {
      case 'home_win':
        return '${m.homeName} won';
      case 'away_win':
        return '${m.awayName} won';
      case 'draw':
        return 'Draw';
      case 'undecided':
        return 'Result undecided';
    }
    return m.status == 'upcoming' ? 'Not started yet' : 'In play';
  }

  Widget _team(BuildContext context, String name, TeamScore s, String teamId) {
    final on = Theme.of(context).colorScheme.onPrimary;
    return InkWell(
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => ClubScreen(clubId: teamId, title: name),
        ),
      ),
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 48),
        child: Column(
          children: [
            Text(
              name,
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: on,
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
            ),
            if (s.wickets != null || s.overs != null)
              Text(
                '${s.wickets ?? 0} wkts, ${s.overs ?? '0.0'} ov',
                style: TextStyle(color: on, fontSize: 12),
              ),
          ],
        ),
      ),
    );
  }

  Widget _pinned(BuildContext context, Product p) {
    final price = p.minPrice;
    return Card(
      color: Theme.of(context).colorScheme.secondaryContainer,
      margin: const EdgeInsets.fromLTRB(12, 12, 12, 0),
      child: ListTile(
        leading: const Icon(
          Icons.local_offer,
          semanticLabel: 'Featured product',
        ),
        title: Text(
          'Featured: ${p.name}',
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
        subtitle: Text(
          price == null ? p.category : 'From ${formatMoney(price)}',
        ),
        trailing: const Text(
          'Shop',
          style: TextStyle(fontWeight: FontWeight.bold),
        ),
        onTap: () => Navigator.of(context)
            .push(MaterialPageRoute(builder: (_) => ProductScreen(product: p))),
      ),
    );
  }

  Widget _eventTile(BuildContext context, MatchDetail m, MatchEvent e) {
    final p = e.payload;
    String title;
    IconData icon;
    switch (e.type) {
      case 'score':
        title =
            '${_cap(p['event_type']?.toString() ?? 'Score')} - ${m.nameFor(p['team_id']?.toString() ?? '')}';
        icon = Icons.sports_soccer;
      case 'discipline':
        title =
            'Discipline (${p['points']}) - ${m.nameFor(p['team_id']?.toString() ?? '')}';
        icon = Icons.style;
      case 'compensation':
        title =
            'Correction of ${p['compensates']}${p['reason'] != null ? ': ${p['reason']}' : ''}';
        icon = Icons.undo;
      case 'match_start':
        title = 'Kick-off';
        icon = Icons.play_circle;
      case 'match_end':
        title = 'Full time';
        icon = Icons.flag;
      case 'match_init':
        title = 'Match created';
        icon = Icons.add_circle_outline;
      case 'tiebreak_winner':
        title = 'Tie-break won by ${m.nameFor(p['team_id']?.toString() ?? '')}';
        icon = Icons.emoji_events;
      default:
        title = e.type;
        icon = Icons.circle_outlined;
    }
    return ListTile(
      leading: CircleAvatar(child: Icon(icon, size: 20, semanticLabel: e.type)),
      title: Text(
        title,
        style: TextStyle(
          decoration: e.compensated ? TextDecoration.lineThrough : null,
        ),
      ),
      subtitle: Text(
        '#${e.sequence}${e.compensated ? ' · Cancelled by a correction' : ''}',
      ),
    );
  }

  String _cap(String s) =>
      s.isEmpty ? s : s[0].toUpperCase() + s.substring(1).replaceAll('_', ' ');
}
