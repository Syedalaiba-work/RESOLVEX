"""Part II §5.9: Prometheus /metrics (NFR-6) and right-to-erasure (NFR-9)."""
import hashlib
import threading

from app.core import ApiError
from app.db import tx

# Live push connections (WebSocket/SSE). The realtime endpoints increment/decrement this.
_ws_lock = threading.Lock()
_ws_connections = 0


def ws_connected(delta: int) -> None:
    global _ws_connections
    with _ws_lock:
        _ws_connections = max(0, _ws_connections + delta)


def metrics_text() -> str:
    with tx() as conn:
        active_streams = conn.execute("SELECT COUNT(*) AS n FROM stream_keys WHERE status = 'active'").fetchone()["n"]
        dlq_depth = conn.execute("SELECT COUNT(*) AS n FROM notification_dlq").fetchone()["n"]
        qr_scans = conn.execute("SELECT COALESCE(SUM(scan_count), 0) AS n FROM qr_codes").fetchone()["n"]
    series = [
        ("nascon_active_ws_connections", "gauge", "Open WebSocket/SSE client connections.", _ws_connections),
        ("nascon_active_streams_total", "gauge", "Stream keys currently active.", active_streams),
        # No media server metrics source yet; reported as 0 rather than an invented value.
        ("nascon_stream_bitrate_kbps", "gauge", "Aggregate ingest bitrate across active streams (kbps).", 0),
        ("nascon_dlq_depth", "gauge", "Notifications waiting in the dead-letter queue.", dlq_depth),
        ("nascon_qr_scans_total", "counter", "Dynamic QR scans recorded (no PII stored).", qr_scans),
    ]
    lines = []
    for name, kind, help_text, value in series:
        lines += [f"# HELP {name} {help_text}", f"# TYPE {name} {kind}", f"{name} {int(value)}"]
    return "\n".join(lines) + "\n"


def erase_user(user_id: str) -> dict:
    with tx() as conn:
        if not conn.execute("SELECT 1 FROM players WHERE player_id = %s", (user_id,)).fetchone():
            raise ApiError(404, "PLAYER_NOT_FOUND", f"Player {user_id} does not exist.", {"user_id": user_id})
        tag = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]
        conn.execute("UPDATE players SET name = 'Anonymized user' WHERE player_id = %s", (user_id,))
        conn.execute(
            "UPDATE users SET email = %s, display_name = 'Anonymized user' WHERE player_id = %s",
            (f"erased-{tag}@invalid", user_id),
        )
        conn.execute("UPDATE guest_tokens SET status = 'wiped', user_id = NULL WHERE user_id = %s", (user_id,))
    return {"user_id": user_id, "status": "anonymized", "pii_retained": False, "tokens_wiped": True}
