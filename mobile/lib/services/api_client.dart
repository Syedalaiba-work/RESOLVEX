import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'error_messages.dart';

/// Error raised by [ApiClient]. [message] is always plain language.
class ApiException implements Exception {
  final String code;
  final int? status;
  final String message;
  final Map<String, dynamic> details;

  ApiException(
    this.code, {
    this.status,
    String? message,
    this.details = const {},
  }) : message = message ?? friendlyError(code, status: status);

  /// True when the server could not be reached at all.
  bool get isNetwork => code == 'NETWORK' || code == 'TIMEOUT';

  @override
  String toString() => message;
}

/// Thin JSON client for /api/v1. Knows nothing about widgets.
class ApiClient {
  final http.Client _http;
  final String Function() baseUrl;
  final String? Function() token;
  final Duration timeout;

  /// Called after every request: true = server reachable, false = network error.
  void Function(bool reachable)? onReachability;

  /// Called when the server answers 401 to an authenticated call.
  void Function()? onUnauthorized;

  ApiClient(
    this._http, {
    required this.baseUrl,
    required this.token,
    this.timeout = const Duration(seconds: 8),
  });

  Uri _uri(String path, [Map<String, String>? query]) {
    var base = baseUrl().trim();
    if (base.endsWith('/')) base = base.substring(0, base.length - 1);
    final u = Uri.parse('$base$path');
    return query == null || query.isEmpty
        ? u
        : u.replace(queryParameters: query);
  }

  Map<String, String> _headers({bool auth = true}) {
    final h = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };
    final t = token();
    if (auth && t != null && t.isNotEmpty) h['Authorization'] = 'Bearer $t';
    return h;
  }

  Future<dynamic> get(
    String path, {
    Map<String, String>? query,
    bool auth = true,
    Duration? timeout,
  }) => _send(
    () => _http.get(_uri(path, query), headers: _headers(auth: auth)),
    auth,
    timeout,
  );

  Future<dynamic> post(String path, Object body, {bool auth = true}) => _send(
    () => _http.post(
      _uri(path),
      headers: _headers(auth: auth),
      body: jsonEncode(body),
    ),
    auth,
    null,
  );

  Future<dynamic> _send(
    Future<http.Response> Function() call,
    bool auth,
    Duration? t,
  ) async {
    http.Response res;
    try {
      res = await call().timeout(t ?? timeout);
    } on TimeoutException {
      // A slow answer is not proof of being offline; the ping loop decides.
      throw ApiException('TIMEOUT');
    } on SocketException {
      onReachability?.call(false);
      throw ApiException('NETWORK');
    } on http.ClientException {
      onReachability?.call(false);
      throw ApiException('NETWORK');
    } on HandshakeException {
      onReachability?.call(false);
      throw ApiException('NETWORK');
    } on FormatException {
      throw ApiException(
        'NETWORK',
        message: 'The server address in Settings is not valid.',
      );
    } on ArgumentError {
      throw ApiException(
        'NETWORK',
        message: 'The server address in Settings is not valid.',
      );
    }
    onReachability?.call(true);
    dynamic body;
    if (res.body.isNotEmpty) {
      try {
        body = jsonDecode(utf8.decode(res.bodyBytes));
      } catch (_) {
        body = null;
      }
    }
    if (res.statusCode >= 200 && res.statusCode < 300) return body;
    String code = 'HTTP_${res.statusCode}';
    Map<String, dynamic> details = const {};
    if (body is Map && body['error'] is Map) {
      final e = body['error'] as Map;
      code = (e['code'] ?? code).toString();
      if (e['details'] is Map) {
        details = Map<String, dynamic>.from(e['details'] as Map);
      }
    }
    if (res.statusCode == 401 && auth) onUnauthorized?.call();
    throw ApiException(code, status: res.statusCode, details: details);
  }
}
