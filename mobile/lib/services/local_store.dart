import 'dart:convert';

import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

import '../models/models.dart';

/// A cached JSON document with the time it was saved.
class CachedJson {
  final dynamic data;
  final DateTime savedAt;
  const CachedJson(this.data, this.savedAt);
}

/// Local persistence: read cache (fixtures, standings, clubs...), key/value
/// settings, and the persistent offline action queue.
abstract class LocalStore {
  Future<void> putCache(String key, dynamic json);
  Future<CachedJson?> getCache(String key);

  Future<String?> getSetting(String key);
  Future<void> setSetting(String key, String value);

  Future<void> enqueue(QueuedAction action);
  Future<List<QueuedAction>> pendingActions();
  Future<void> removeActions(Iterable<String> actionIds);
}

/// SQLite implementation (sqflite). Data survives force-close and reboot.
class SqliteLocalStore implements LocalStore {
  Database? _db;

  Future<Database> get _database async {
    final existing = _db;
    if (existing != null) return existing;
    final dir = await getDatabasesPath();
    final db = await openDatabase(
      p.join(dir, 'nascon_league.db'),
      version: 1,
      onCreate: (db, _) async {
        await db.execute(
          'CREATE TABLE cache (key TEXT PRIMARY KEY, json TEXT NOT NULL, saved_at TEXT NOT NULL)',
        );
        await db.execute(
          'CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
        );
        await db.execute(
          'CREATE TABLE action_queue (seq INTEGER PRIMARY KEY AUTOINCREMENT, '
          'action_id TEXT NOT NULL UNIQUE, action_json TEXT NOT NULL, label TEXT NOT NULL)',
        );
      },
    );
    _db = db;
    return db;
  }

  @override
  Future<void> putCache(String key, dynamic json) async {
    final db = await _database;
    await db.insert('cache', {
      'key': key,
      'json': jsonEncode(json),
      'saved_at': DateTime.now().toUtc().toIso8601String(),
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  @override
  Future<CachedJson?> getCache(String key) async {
    final db = await _database;
    final rows = await db.query('cache', where: 'key = ?', whereArgs: [key]);
    if (rows.isEmpty) return null;
    return CachedJson(
      jsonDecode(rows.first['json'] as String),
      DateTime.tryParse(rows.first['saved_at'] as String) ?? DateTime.now(),
    );
  }

  @override
  Future<String?> getSetting(String key) async {
    final db = await _database;
    final rows = await db.query('settings', where: 'key = ?', whereArgs: [key]);
    return rows.isEmpty ? null : rows.first['value'] as String;
  }

  @override
  Future<void> setSetting(String key, String value) async {
    final db = await _database;
    await db.insert('settings', {
      'key': key,
      'value': value,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  @override
  Future<void> enqueue(QueuedAction action) async {
    final db = await _database;
    await db.insert('action_queue', {
      'action_id': action.actionId,
      'action_json': jsonEncode(action.toJson()),
      'label': action.label,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  @override
  Future<List<QueuedAction>> pendingActions() async {
    final db = await _database;
    final rows = await db.query('action_queue', orderBy: 'seq ASC');
    return rows
        .map(
          (r) => QueuedAction.fromJson(
            Map<String, dynamic>.from(
              jsonDecode(r['action_json'] as String) as Map,
            ),
            label: r['label'] as String,
          ),
        )
        .toList();
  }

  @override
  Future<void> removeActions(Iterable<String> actionIds) async {
    final db = await _database;
    final batch = db.batch();
    for (final id in actionIds) {
      batch.delete('action_queue', where: 'action_id = ?', whereArgs: [id]);
    }
    await batch.commit(noResult: true);
  }
}

/// In-memory implementation for tests (JSON round-trips like the real one).
class MemoryLocalStore implements LocalStore {
  final Map<String, CachedJson> cache = {};
  final Map<String, String> settings = {};
  final List<QueuedAction> queue = [];

  @override
  Future<void> putCache(String key, dynamic json) async =>
      cache[key] = CachedJson(jsonDecode(jsonEncode(json)), DateTime.now());

  @override
  Future<CachedJson?> getCache(String key) async => cache[key];

  @override
  Future<String?> getSetting(String key) async => settings[key];

  @override
  Future<void> setSetting(String key, String value) async =>
      settings[key] = value;

  @override
  Future<void> enqueue(QueuedAction action) async {
    queue.removeWhere((a) => a.actionId == action.actionId);
    queue.add(action);
  }

  @override
  Future<List<QueuedAction>> pendingActions() async => List.of(queue);

  @override
  Future<void> removeActions(Iterable<String> actionIds) async {
    final ids = actionIds.toSet();
    queue.removeWhere((a) => ids.contains(a.actionId));
  }
}
