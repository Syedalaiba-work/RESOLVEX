"""Internal queue consumer: processes structured domain events from the outbox table.

Producers (checkout, payment failures) insert into domain_events in the same transaction as the
state change; this worker picks them up with SKIP LOCKED so several workers could run safely.
"""
import json
import logging
import time

from app.db import create_schema, tx, wait_for_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s worker %(message)s")
log = logging.getLogger("worker")


def process_batch(limit: int = 50) -> int:
    with tx() as conn:
        rows = conn.execute(
            "SELECT id, type, payload FROM domain_events WHERE processed_at IS NULL "
            "ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED", (limit,)).fetchall()
        for row in rows:
            # Real side effects (emails, notifications, analytics) would go here.
            log.info("event %s %s %s", row["id"], row["type"], json.dumps(row["payload"]))
            conn.execute("UPDATE domain_events SET processed_at = now() WHERE id = %s", (row["id"],))
    return len(rows)


def main() -> None:
    wait_for_db()
    create_schema()
    log.info("started")
    while True:
        try:
            if process_batch() == 0:
                time.sleep(1)
        except Exception:
            log.exception("batch failed; retrying")
            time.sleep(2)


if __name__ == "__main__":
    main()
