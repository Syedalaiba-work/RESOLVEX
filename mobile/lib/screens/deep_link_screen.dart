import 'dart:async';

import 'package:flutter/material.dart';

import '../services/app_state.dart';
import '../widgets/common.dart';

/// Part II §6.3: `nascon://entity/{id}` and `nascon://stream/{id}` open here directly, on top of
/// whatever is underneath (including the login screen). Flutter passes the URI path as the initial
/// route, so `nascon://entity/match-m1` arrives as `/match-m1`.
Route<dynamic>? deepLinkRoute(RouteSettings settings) {
  final name = settings.name ?? '';
  final id = name.startsWith('/') ? name.substring(1) : name;
  if (id.startsWith('match-') || id.startsWith('cs-session-')) {
    return MaterialPageRoute(
      settings: settings,
      builder: (_) => DeepLinkScreen(entityId: id),
    );
  }
  return null;
}

class DeepLinkScreen extends StatefulWidget {
  final String entityId;
  const DeepLinkScreen({super.key, required this.entityId});

  bool get isMatch => entityId.startsWith('match-');

  @override
  State<DeepLinkScreen> createState() => _DeepLinkScreenState();
}

class _DeepLinkScreenState extends State<DeepLinkScreen> {
  Map<String, dynamic>? _match;
  String? _error;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    if (widget.isMatch) {
      _load();
      _timer = Timer.periodic(const Duration(seconds: 3), (_) => _load());
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      // Public, read-only summary: no sign-in needed for a scanned link (FR-4.2).
      final j = await AppScope.read(context).api.get(
        '/web/api/matches/${Uri.encodeComponent(widget.entityId)}',
        auth: false,
      );
      if (mounted) {
        setState(() {
          _match = j as Map<String, dynamic>;
          _error = null;
        });
      }
    } catch (_) {
      if (mounted && _match == null) {
        setState(
          () =>
              _error = 'This match could not be loaded. Check your connection.',
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final title = widget.isMatch
        ? 'Match live: ${widget.entityId}'
        : 'Co-stream: ${widget.entityId}';
    return Scaffold(
      appBar: AppBar(
        title: Semantics(
          label: title,
          excludeSemantics:
              true, // one clean label; the title is not interactive
          child: Text(widget.isMatch ? 'Match live' : 'Co-stream'),
        ),
      ),
      body: ListView(
        children: [
          Container(
            margin: heroMargin,
            decoration: heroDecoration(),
            padding: const EdgeInsets.all(20),
            child: widget.isMatch ? _matchHero() : _costreamHero(),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                _error!,
                style: const TextStyle(color: AppColors.danger),
              ),
            ),
        ],
      ),
    );
  }

  Widget _matchHero() {
    final m = _match;
    if (m == null) {
      return const Center(
        child: CircularProgressIndicator(color: AppColors.lime),
      );
    }
    final home = m['home'] as Map<String, dynamic>;
    final away = m['away'] as Map<String, dynamic>;
    final score = m['score_text'] as String;
    return Semantics(
      label:
          'Score: ${home['name']} ${home['score']}, ${away['name']} ${away['score']}',
      child: Column(
        children: [
          MatchStatusBadge(status: m['status'] as String),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: Text(
                  '${home['name']}',
                  textAlign: TextAlign.center,
                  style: _team,
                ),
              ),
              AnimatedScore(
                score,
                style: const TextStyle(
                  fontSize: 40,
                  fontWeight: FontWeight.w900,
                  color: AppColors.lime,
                ),
              ),
              Expanded(
                child: Text(
                  '${away['name']}',
                  textAlign: TextAlign.center,
                  style: _team,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _costreamHero() => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(widget.entityId, style: _team),
      const SizedBox(height: 8),
      Text(
        'Chat room: chat-${widget.entityId}',
        style: const TextStyle(color: Colors.white70),
      ),
    ],
  );

  static const _team = TextStyle(
    color: Colors.white,
    fontSize: 16,
    fontWeight: FontWeight.w700,
  );
}
