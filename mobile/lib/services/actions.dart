import 'api_client.dart';
import 'app_state.dart';

enum ActionOutcome { sent, queued }

/// Runs a write action online when possible; when offline (or the network
/// fails mid-request) stores it in the persistent queue in the spec 5.14
/// action format so it can be synced later.
Future<ActionOutcome> performOrQueue(
  AppState app, {
  required String type, // score_event | roster_transfer
  required int baseVersion,
  required Map<String, dynamic> payload,
  required String label,
  required Future<void> Function() online,
}) async {
  Future<ActionOutcome> queue() async {
    await app.sync.enqueue(
      type: type,
      baseVersion: baseVersion,
      payload: payload,
      label: label,
    );
    return ActionOutcome.queued;
  }

  if (!app.connectivity.isOnline) return queue();
  try {
    await online();
    return ActionOutcome.sent;
  } on ApiException catch (e) {
    if (e.isNetwork) return queue();
    rethrow;
  }
}
