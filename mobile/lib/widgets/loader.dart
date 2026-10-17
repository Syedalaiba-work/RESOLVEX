import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../services/app_state.dart';
import '../services/connectivity_service.dart';
import '../services/repository.dart';
import 'common.dart';

/// Loads data via [load] and renders loading / error / cached states uniformly.
class Loader<T> extends StatefulWidget {
  final Future<Loaded<T>> Function() load;
  final Widget Function(
    BuildContext context,
    T data,
    Future<void> Function() refresh,
  )
  builder;
  final String loadingMessage;
  final Object? reloadKey;

  const Loader({
    super.key,
    required this.load,
    required this.builder,
    this.loadingMessage = 'Loading...',
    this.reloadKey,
  });

  @override
  State<Loader<T>> createState() => _LoaderState<T>();
}

class _LoaderState<T> extends State<Loader<T>> {
  Loaded<T>? _data;
  String? _error;
  bool _loading = true;

  ConnectivityService? _conn;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final c = AppScope.read(context).connectivity;
    if (!identical(c, _conn)) {
      _conn?.removeListener(_onConnectivity);
      _conn = c..addListener(_onConnectivity);
    }
  }

  /// When the connection comes back, replace cached data (or an error) with fresh data.
  void _onConnectivity() {
    final c = _conn;
    if (!mounted || c == null || !c.isOnline || _loading) return;
    if (_data == null || _data!.fromCache) _refresh();
  }

  @override
  void dispose() {
    _conn?.removeListener(_onConnectivity);
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant Loader<T> oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.reloadKey != widget.reloadKey) {
      _data = null;
      _refresh();
    }
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final d = await widget.load();
      if (!mounted) return;
      setState(() {
        _data = d;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.isNetwork
            ? 'You are offline and this page has not been saved on this phone yet. '
                  'Open it once while online to keep a copy.'
            : e.message;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error =
            'Something went wrong while showing this page. Please try again.';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = _data;
    if (d == null) {
      if (_loading) return LoadingView(message: widget.loadingMessage);
      return ErrorView(
        message: _error ?? 'Unknown problem.',
        onRetry: _refresh,
      );
    }
    return Column(
      children: [
        if (d.fromCache) CachedBanner(savedAt: d.savedAt),
        if (_loading) const LinearProgressIndicator(minHeight: 3),
        if (_error != null && !_loading)
          Material(
            color: const Color(0xFFFFEBEE),
            child: ListTile(
              leading: const Icon(
                Icons.error_outline,
                color: Color(0xFFB71C1C),
                semanticLabel: 'Error',
              ),
              title: Text(_error!),
            ),
          ),
        Expanded(child: widget.builder(context, d.data, _refresh)),
      ],
    );
  }
}
