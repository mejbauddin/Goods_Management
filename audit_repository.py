"""Read-only access to the audit log.

Improvements over the original version:
  * Corrupt or non-object JSON in the log no longer crashes the page.
  * Shared helpers remove the repeated JSON/connection code.
  * `compute_changes()` is the single place that diffs two snapshots
    (used by the history page and the command-line tool).
  * Optional `limit`, a recent-activity query, and an index helper.
  * The command-line tool accepts any goods ID.

Public names used elsewhere are unchanged:
  get_goods_history(goods_id) and get_deleted_goods().
"""

import json
import sys
from contextlib import closing

from database import get_connection

# Business fields shown when comparing two versions of a goods record.
TRACKED_FIELDS = {
    "code": "Goods code",
    "name": "Goods name",
    "category_id": "Category ID",
    "unit": "Unit",
    "weight": "Weight per unit (kg)",
    "description": "Description",
    "status": "Status",
    "photo_filename": "Photo filename",
}


def _load_snapshot(raw):
    """Parse a JSON snapshot; return {} for missing, invalid or odd data."""
    if raw is None:
        return {}

    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}

    return data if isinstance(data, dict) else {}


def compute_changes(before, after, fields=None):
    """Return [{'label', 'before', 'after'}] for fields that differ."""
    fields = fields or TRACKED_FIELDS

    return [
        {
            "label": label,
            "before": before.get(field),
            "after": after.get(field),
        }
        for field, label in fields.items()
        if before.get(field) != after.get(field)
    ]


def ensure_audit_indexes():
    """Speed up history lookups. Safe to call repeatedly."""
    with closing(get_connection()) as connection:
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_entity
            ON audit_log (entity_type, entity_id, id)
            """
        )
        connection.commit()


def get_goods_history(goods_id, limit=None):
    """Read a goods record's history, newest first."""
    query = """
        SELECT
            id,
            entity_id,
            entity_label,
            action,
            before_json,
            after_json,
            created_at
        FROM audit_log
        WHERE entity_type = 'goods'
          AND entity_id = ?
        ORDER BY id DESC
    """
    params = [goods_id]

    if limit is not None:
        query += " LIMIT ?"
        params.append(int(limit))

    with closing(get_connection()) as connection:
        rows = connection.execute(query, params).fetchall()

    history = []

    for row in rows:
        entry = dict(row)
        entry["before"] = _load_snapshot(entry["before_json"])
        entry["after"] = _load_snapshot(entry["after_json"])
        history.append(entry)

    return history


def get_deleted_goods():
    """List permanently deleted goods with their last saved details."""
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT
                audit_log.entity_id,
                audit_log.entity_label,
                audit_log.before_json,
                audit_log.created_at AS deleted_at
            FROM audit_log
            WHERE audit_log.entity_type = 'goods'
              AND audit_log.action = 'deleted'
              AND NOT EXISTS (
                  SELECT 1
                  FROM goods
                  WHERE goods.id = audit_log.entity_id
              )
            ORDER BY audit_log.id DESC
            """
        ).fetchall()

    deleted_goods = []

    for row in rows:
        snapshot = _load_snapshot(row["before_json"])

        deleted_goods.append({
            "id": row["entity_id"],
            "code": snapshot.get("code", row["entity_label"]),
            "name": snapshot.get("name", "Deleted goods"),
            "deleted_at": row["deleted_at"],
        })

    return deleted_goods


def get_recent_activity(limit=10):
    """Latest audit events across all goods (handy for a dashboard feed)."""
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT id, entity_id, entity_label, action, created_at
            FROM audit_log
            WHERE entity_type = 'goods'
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    return [dict(row) for row in rows]


def _print_history(goods_id):
    history = get_goods_history(goods_id)

    if not history:
        print(f"No history found for goods ID {goods_id}.")
        return

    for entry in history:
        print(
            f"\n{entry['created_at']} UTC | "
            f"{entry['action'].upper()} | "
            f"{entry['entity_label']}"
        )

        for change in compute_changes(entry["before"], entry["after"]):
            print(
                f"  {change['label']}: "
                f"{change['before']!r} -> {change['after']!r}"
            )


if __name__ == "__main__":
    # Usage: python audit_repository.py [goods_id]
    try:
        target_id = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    except ValueError:
        sys.exit("Usage: python audit_repository.py [goods_id]")

    _print_history(target_id)
