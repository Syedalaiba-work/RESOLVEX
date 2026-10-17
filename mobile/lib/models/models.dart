// Plain data models parsed from the /api/v1 JSON contract.
// Parsing is defensive: missing fields fall back to sensible defaults so a
// partially implemented backend never crashes the UI.

String _s(dynamic v, [String fallback = '']) =>
    v == null ? fallback : v.toString();
int _i(dynamic v, [int fallback = 0]) {
  if (v is int) return v;
  if (v is num) return v.toInt();
  if (v is String) return int.tryParse(v) ?? fallback;
  return fallback;
}

String? _ns(dynamic v) => v?.toString();
Map<String, dynamic> _m(dynamic v) =>
    v is Map ? Map<String, dynamic>.from(v) : <String, dynamic>{};
List<dynamic> _l(dynamic v) => v is List ? v : const [];

class Roles {
  static const superAdmin = 'super_admin';
  static const organizer = 'league_organizer';
  static const manager = 'club_manager';
  static const player = 'player';
  static const viewer = 'viewer';

  static String label(String role) {
    switch (role) {
      case superAdmin:
        return 'Platform Super-Admin';
      case organizer:
        return 'League Organizer';
      case manager:
        return 'Club Manager';
      case player:
        return 'Player';
      case viewer:
        return 'Viewer';
    }
    return role;
  }
}

class AppUser {
  final String email;
  final String role;
  final String displayName;
  final String? tenantId;
  final String? leagueId;
  final String? clubId;
  final String? playerId;

  const AppUser({
    required this.email,
    required this.role,
    required this.displayName,
    this.tenantId,
    this.leagueId,
    this.clubId,
    this.playerId,
  });

  bool get canScore => role == Roles.organizer || role == Roles.superAdmin;
  bool get canManageRoster => role == Roles.manager || role == Roles.superAdmin;

  factory AppUser.fromJson(Map<String, dynamic> j) => AppUser(
    email: _s(j['email']),
    role: _s(j['role'], Roles.viewer),
    displayName: _s(j['display_name'], _s(j['email'])),
    tenantId: _ns(j['tenant_id']),
    leagueId: _ns(j['league_id']),
    clubId: _ns(j['club_id']),
    playerId: _ns(j['player_id']),
  );

  Map<String, dynamic> toJson() => {
    'email': email,
    'role': role,
    'display_name': displayName,
    'tenant_id': tenantId,
    'league_id': leagueId,
    'club_id': clubId,
    'player_id': playerId,
  };
}

class Tenant {
  final String tenantId;
  final String name;
  final String? primaryColor;
  final String? accentColor;
  final String? logoText;

  const Tenant({
    required this.tenantId,
    required this.name,
    this.primaryColor,
    this.accentColor,
    this.logoText,
  });

  factory Tenant.fromJson(Map<String, dynamic> j) {
    final b = _m(j['branding']);
    return Tenant(
      tenantId: _s(j['tenant_id']),
      name: _s(j['name']),
      primaryColor: _ns(b['primary_color']),
      accentColor: _ns(b['accent_color']),
      logoText: _ns(b['logo_text']),
    );
  }

  Map<String, dynamic> toJson() => {
    'tenant_id': tenantId,
    'name': name,
    'branding': {
      'primary_color': primaryColor,
      'accent_color': accentColor,
      'logo_text': logoText,
    },
  };
}

class League {
  final String leagueId;
  final String name;
  final String sportId;
  final String? tenantId;

  const League({
    required this.leagueId,
    required this.name,
    required this.sportId,
    this.tenantId,
  });

  factory League.fromJson(Map<String, dynamic> j) => League(
    leagueId: _s(j['league_id']),
    name: _s(j['name'], _s(j['league_id'])),
    sportId: _s(j['sport_id']),
    tenantId: _ns(j['tenant_id']),
  );
}

class Fixture {
  final String matchId;
  final String? leagueId;
  final String sportId;
  final String homeTeamId;
  final String awayTeamId;
  final String homeName;
  final String awayName;
  final String status;
  final String? scheduledAt;
  final int? homeScore;
  final int? awayScore;

  const Fixture({
    required this.matchId,
    this.leagueId,
    required this.sportId,
    required this.homeTeamId,
    required this.awayTeamId,
    required this.homeName,
    required this.awayName,
    required this.status,
    this.scheduledAt,
    this.homeScore,
    this.awayScore,
  });

  factory Fixture.fromJson(Map<String, dynamic> j) => Fixture(
    matchId: _s(j['match_id']),
    leagueId: _ns(j['league_id']),
    sportId: _s(j['sport_id']),
    homeTeamId: _s(j['home_team_id']),
    awayTeamId: _s(j['away_team_id']),
    homeName: _s(j['home_name'], _s(j['home_team_id'])),
    awayName: _s(j['away_name'], _s(j['away_team_id'])),
    status: _s(j['status'], 'upcoming'),
    scheduledAt: _ns(j['scheduled_at']),
    homeScore: j['home_score'] == null ? null : _i(j['home_score']),
    awayScore: j['away_score'] == null ? null : _i(j['away_score']),
  );
}

class TeamScore {
  final String teamId;
  final int score;
  final int? wickets;
  final String? overs;
  final int fairPlay;

  const TeamScore({
    required this.teamId,
    required this.score,
    this.wickets,
    this.overs,
    this.fairPlay = 0,
  });

  factory TeamScore.fromJson(Map<String, dynamic> j) => TeamScore(
    teamId: _s(j['team_id']),
    score: _i(j['score']),
    wickets: j['wickets'] == null ? null : _i(j['wickets']),
    overs: _ns(j['overs']),
    fairPlay: _i(j['fair_play']),
  );
}

class MatchEvent {
  final int sequence;
  final String eventId;
  final String type;
  final Map<String, dynamic> payload;
  final bool compensated;
  final String? compensatedBy;

  const MatchEvent({
    required this.sequence,
    required this.eventId,
    required this.type,
    required this.payload,
    this.compensated = false,
    this.compensatedBy,
  });

  factory MatchEvent.fromJson(Map<String, dynamic> j) => MatchEvent(
    sequence: _i(j['sequence']),
    eventId: _s(j['event_id']),
    type: _s(j['type']),
    payload: _m(j['payload']),
    compensated: j['compensated'] == true,
    compensatedBy: _ns(j['compensated_by']),
  );

  /// Events that may be targeted by a compensating event.
  bool get compensatable =>
      !compensated &&
      (type == 'score' || type == 'discipline' || type == 'tiebreak_winner');
}

class MatchDetail {
  final String matchId;
  final String sportId;
  final String? leagueId;
  final String status;
  final String outcome;
  final String? winnerTeamId;
  final TeamScore home;
  final TeamScore away;
  final String homeName;
  final String awayName;
  final String? scheduledAt;
  final int version;
  final List<MatchEvent> events;
  final Product? pinnedProduct;

  const MatchDetail({
    required this.matchId,
    required this.sportId,
    this.leagueId,
    required this.status,
    required this.outcome,
    this.winnerTeamId,
    required this.home,
    required this.away,
    required this.homeName,
    required this.awayName,
    this.scheduledAt,
    required this.version,
    required this.events,
    this.pinnedProduct,
  });

  String nameFor(String teamId) => teamId == home.teamId
      ? homeName
      : (teamId == away.teamId ? awayName : teamId);

  factory MatchDetail.fromJson(Map<String, dynamic> j) {
    final home = TeamScore.fromJson(_m(j['home']));
    final away = TeamScore.fromJson(_m(j['away']));
    final pinned = j['pinned_product'];
    return MatchDetail(
      matchId: _s(j['match_id']),
      sportId: _s(j['sport_id']),
      leagueId: _ns(j['league_id']),
      status: _s(j['status'], 'upcoming'),
      outcome: _s(j['outcome'], 'pending'),
      winnerTeamId: _ns(j['winner_team_id']),
      home: home,
      away: away,
      homeName: _s(j['home_name'], home.teamId),
      awayName: _s(j['away_name'], away.teamId),
      scheduledAt: _ns(j['scheduled_at']),
      version: _i(j['version']),
      events: _l(j['events']).map((e) => MatchEvent.fromJson(_m(e))).toList(),
      pinnedProduct: pinned is Map ? Product.fromJson(_m(pinned)) : null,
    );
  }
}

class StandingRow {
  final int rank;
  final String teamId;
  final int played, won, drawn, lost, scored, conceded, points, fairPlay;
  final num diff;
  final String status;

  const StandingRow({
    required this.rank,
    required this.teamId,
    required this.played,
    required this.won,
    required this.drawn,
    required this.lost,
    required this.scored,
    required this.conceded,
    required this.diff,
    required this.points,
    required this.fairPlay,
    required this.status,
  });

  factory StandingRow.fromJson(Map<String, dynamic> j) => StandingRow(
    rank: _i(j['rank']),
    teamId: _s(j['team_id']),
    played: _i(j['played']),
    won: _i(j['won']),
    drawn: _i(j['drawn']),
    lost: _i(j['lost']),
    scored: _i(j['scored']),
    conceded: _i(j['conceded']),
    diff: j['diff'] is num
        ? j['diff'] as num
        : num.tryParse(_s(j['diff'])) ?? 0,
    points: _i(j['points']),
    fairPlay: _i(j['fair_play']),
    status: _s(j['status'], 'still_possible'),
  );
}

class Standings {
  final String leagueId;
  final int qualificationSpots;
  final List<StandingRow> table;
  final Map<String, String> names;

  const Standings({
    required this.leagueId,
    required this.qualificationSpots,
    required this.table,
    required this.names,
  });

  String nameFor(String teamId) => names[teamId] ?? teamId;

  factory Standings.fromJson(Map<String, dynamic> j) => Standings(
    leagueId: _s(j['league_id']),
    qualificationSpots: _i(j['qualification_spots']),
    table: _l(j['table']).map((e) => StandingRow.fromJson(_m(e))).toList(),
    names: _m(j['names']).map((k, v) => MapEntry(k, _s(v))),
  );
}

class ClubSummary {
  final String clubId;
  final String name;
  const ClubSummary({required this.clubId, required this.name});
  factory ClubSummary.fromJson(Map<String, dynamic> j) => ClubSummary(
    clubId: _s(j['club_id']),
    name: _s(j['name'], _s(j['club_id'])),
  );
}

class RosterPlayer {
  final String playerId;
  final String name;
  final String position;
  final String role;
  final String? squadId;

  const RosterPlayer({
    required this.playerId,
    required this.name,
    required this.position,
    required this.role,
    this.squadId,
  });

  factory RosterPlayer.fromJson(Map<String, dynamic> j) => RosterPlayer(
    playerId: _s(j['player_id']),
    name: _s(j['name'], _s(j['player_id'])),
    position: _s(j['position']),
    role: _s(j['role']),
    squadId: _ns(j['squad_id']),
  );
}

class ClubProfile {
  final String clubId;
  final String name;
  final String? homeVenue;
  final Map<String, dynamic> social;
  final List<Map<String, dynamic>> staff;
  final dynamic history;
  final List<RosterPlayer> roster;

  const ClubProfile({
    required this.clubId,
    required this.name,
    this.homeVenue,
    required this.social,
    required this.staff,
    this.history,
    required this.roster,
  });

  factory ClubProfile.fromJson(Map<String, dynamic> j) {
    final venue = j['home_venue'];
    String? venueText;
    if (venue is Map) {
      venueText = [
        venue['name'],
        venue['city'],
        venue['address'],
      ].where((e) => e != null && e.toString().isNotEmpty).join(', ');
    } else if (venue != null) {
      venueText = venue.toString();
    }
    final staffRaw = j['staff'];
    final staff = <Map<String, dynamic>>[];
    if (staffRaw is List) {
      for (final s in staffRaw) {
        staff.add(s is Map ? _m(s) : {'name': s.toString()});
      }
    } else if (staffRaw is Map) {
      staffRaw.forEach(
        (k, v) => staff.add({'role': k.toString(), 'name': v.toString()}),
      );
    }
    return ClubProfile(
      clubId: _s(j['club_id']),
      name: _s(j['name'], _s(j['club_id'])),
      homeVenue: venueText,
      social: _m(j['social']),
      staff: staff,
      history: j['history'],
      roster: _l(j['roster']).map((e) => RosterPlayer.fromJson(_m(e))).toList(),
    );
  }
}

class Variant {
  final String variantId;
  final String label;
  final int priceMinor;
  final String currency;
  final int stock;

  const Variant({
    required this.variantId,
    required this.label,
    required this.priceMinor,
    required this.currency,
    required this.stock,
  });

  factory Variant.fromJson(Map<String, dynamic> j) => Variant(
    variantId: _s(j['variant_id']),
    label: _s(j['label'], _s(j['variant_id'])),
    priceMinor: _i(j['price_minor']),
    currency: _s(j['currency'], 'PKR'),
    stock: _i(j['stock']),
  );
}

class Product {
  final String productId;
  final String name;
  final String category;
  final String description;
  final String? clubId;
  final List<Variant> variants;

  const Product({
    required this.productId,
    required this.name,
    required this.category,
    required this.description,
    this.clubId,
    required this.variants,
  });

  int? get minPrice => variants.isEmpty
      ? null
      : variants.map((v) => v.priceMinor).reduce((a, b) => a < b ? a : b);

  factory Product.fromJson(Map<String, dynamic> j) => Product(
    productId: _s(j['product_id']),
    name: _s(j['name'], _s(j['product_id'])),
    category: _s(j['category']),
    description: _s(j['description']),
    clubId: _ns(j['club_id']),
    variants: _l(j['variants']).map((e) => Variant.fromJson(_m(e))).toList(),
  );
}

class CartLine {
  final Product product;
  final Variant variant;
  int quantity;
  CartLine({required this.product, required this.variant, this.quantity = 1});
  int get totalMinor => variant.priceMinor * quantity;
}

class Squad {
  final String squadId;
  final String clubId;
  final String name;
  final List<RosterPlayer> players;
  const Squad({
    required this.squadId,
    required this.clubId,
    required this.name,
    required this.players,
  });

  factory Squad.fromJson(Map<String, dynamic> j) {
    final id = _s(j['squad_id']);
    return Squad(
      squadId: id,
      clubId: _s(j['club_id']),
      name: _s(j['name'], id),
      players: _l(j['players']).map((e) {
        final m = _m(e);
        m['squad_id'] ??= id;
        return RosterPlayer.fromJson(m);
      }).toList(),
    );
  }
}

class RosterView {
  final String leagueId;
  final List<Squad> squads;
  final String? windowOpen;
  final String? windowClose;

  const RosterView({
    required this.leagueId,
    required this.squads,
    this.windowOpen,
    this.windowClose,
  });

  factory RosterView.fromJson(Map<String, dynamic> j) {
    final w = _m(j['transfer_window']);
    return RosterView(
      leagueId: _s(j['league_id']),
      squads: _l(j['squads']).map((e) => Squad.fromJson(_m(e))).toList(),
      windowOpen: _ns(w['open']),
      windowClose: _ns(w['close']),
    );
  }
}

/// One entry of the persistent offline queue. [toJson] is EXACTLY the
/// spec 5.14 action format; [label] is a local, human readable description.
class QueuedAction {
  final String actionId;
  final String type; // score_event | roster_transfer
  final String queuedAt; // YYYY-MM-DDTHH:MM:SSZ
  final int baseVersion;
  final Map<String, dynamic> payload;
  final String label;

  const QueuedAction({
    required this.actionId,
    required this.type,
    required this.queuedAt,
    required this.baseVersion,
    required this.payload,
    this.label = '',
  });

  Map<String, dynamic> toJson() => {
    'action_id': actionId,
    'type': type,
    'queued_at': queuedAt,
    'base_version': baseVersion,
    'payload': payload,
  };

  factory QueuedAction.fromJson(Map<String, dynamic> j, {String label = ''}) =>
      QueuedAction(
        actionId: _s(j['action_id']),
        type: _s(j['type']),
        queuedAt: _s(j['queued_at']),
        baseVersion: _i(j['base_version']),
        payload: _m(j['payload']),
        label: label,
      );
}

class SyncResult {
  final String actionId;
  final String status; // applied | rejected | duplicate
  final String? resolution;
  final String? errorCode;
  final int? processedOrder;
  final int? serverVersion;
  final String label;

  const SyncResult({
    required this.actionId,
    required this.status,
    this.resolution,
    this.errorCode,
    this.processedOrder,
    this.serverVersion,
    this.label = '',
  });

  factory SyncResult.fromJson(Map<String, dynamic> j) => SyncResult(
    actionId: _s(j['action_id']),
    status: _s(j['status']),
    resolution: _ns(j['resolution']),
    errorCode: _ns(j['error_code']),
    processedOrder: j['processed_order'] == null
        ? null
        : _i(j['processed_order']),
    serverVersion: j['server_version'] == null ? null : _i(j['server_version']),
    label: _s(j['label']),
  );

  Map<String, dynamic> toJson() => {
    'action_id': actionId,
    'status': status,
    'resolution': resolution,
    'error_code': errorCode,
    'processed_order': processedOrder,
    'server_version': serverVersion,
    'label': label,
  };
}

class CheckoutResult {
  final String orderId;
  final String status;
  final String currency;
  final List<Map<String, dynamic>> items;
  final int subtotalMinor;
  final int discountMinor;
  final int totalMinor;
  final String? paidAt;
  final String? signature;
  final String? pdfBase64;

  const CheckoutResult({
    required this.orderId,
    required this.status,
    required this.currency,
    required this.items,
    required this.subtotalMinor,
    required this.discountMinor,
    required this.totalMinor,
    this.paidAt,
    this.signature,
    this.pdfBase64,
  });

  factory CheckoutResult.fromJson(Map<String, dynamic> j) {
    final receipt = _m(j['receipt']);
    final payload = _m(receipt['payload']);
    return CheckoutResult(
      orderId: _s(j['order_id']),
      status: _s(j['status']),
      currency: _s(j['currency'], 'PKR'),
      items: _l(j['items']).map((e) => _m(e)).toList(),
      subtotalMinor: _i(j['subtotal_minor']),
      discountMinor: _i(j['discount_minor']),
      totalMinor: _i(j['total_minor']),
      paidAt: _ns(payload['paid_at']),
      signature: _ns(receipt['signature']),
      pdfBase64: _ns(receipt['pdf_base64']),
    );
  }
}

String formatMoney(int minor, [String currency = 'PKR']) {
  final major = minor ~/ 100;
  final cents = (minor % 100).toString().padLeft(2, '0');
  final digits = major.toString();
  final buf = StringBuffer();
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) buf.write(',');
    buf.write(digits[i]);
  }
  return '$currency $buf.$cents';
}

/// UTC timestamp in the contract format YYYY-MM-DDTHH:MM:SSZ.
String utcStamp([DateTime? t]) {
  final d = (t ?? DateTime.now()).toUtc();
  String two(int n) => n.toString().padLeft(2, '0');
  return '${d.year.toString().padLeft(4, '0')}-${two(d.month)}-${two(d.day)}T'
      '${two(d.hour)}:${two(d.minute)}:${two(d.second)}Z';
}

String isoDate(DateTime d) {
  String two(int n) => n.toString().padLeft(2, '0');
  return '${d.year.toString().padLeft(4, '0')}-${two(d.month)}-${two(d.day)}';
}

/// Human friendly local time for a contract timestamp.
String friendlyTime(String? stamp) {
  if (stamp == null || stamp.isEmpty) return 'Time to be announced';
  final d = DateTime.tryParse(stamp);
  if (d == null) return stamp;
  final l = d.toLocal();
  const months = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ];
  String two(int n) => n.toString().padLeft(2, '0');
  return '${l.day} ${months[l.month - 1]} ${l.year}, ${two(l.hour)}:${two(l.minute)}';
}

String statusLabel(String status) {
  switch (status) {
    case 'in_progress':
      return 'LIVE';
    case 'completed':
      return 'Full time';
    case 'upcoming':
      return 'Upcoming';
  }
  return status.replaceAll('_', ' ');
}
