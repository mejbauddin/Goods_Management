"""Operational flow metrics for the GoodsHub control room.

This module turns the transactional tables (goods, categories, audit_log)
into the numbers the Operations pages animate: lifecycle volumes, pipeline
throughput, a 14-day activity matrix, completeness ratios and a live feed.

All reads happen on a single connection so the diagrams on one screen are
consistent with each other. The old repository modules stay untouched, so
nothing here can break the CRUD flows.
"""

from contextlib import closing
from datetime import datetime, timedelta, timezone

from database import get_connection

ACTIONS = (
    "created", "updated", "archived", "restored", "deleted", "photo_updated",
)

# Human wording used in the activity stream and flow legends.
ACTION_WORDS = {
    "created": "registered",
    "updated": "edited",
    "archived": "archived",
    "restored": "restored",
    "deleted": "purged",
    "photo_updated": "photo replaced",
}


def _pct(part, whole, digits=1):
    if not whole:
        return 0.0
    return round(part * 100 / whole, digits)


def _days(count):
    """Return the last `count` UTC days as YYYY-MM-DD, oldest first."""
    today = datetime.now(timezone.utc).date()
    return [
        (today - timedelta(days=offset)).isoformat()
        for offset in range(count - 1, -1, -1)
    ]


def get_ops_snapshot(days=14):
    """Return everything the Operations flow pages need, in one snapshot."""
    days = max(3, min(int(days), 60))
    window = _days(days)
    window_start = window[0] + " 00:00:00"
    horizon = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    with closing(get_connection()) as connection:
        connection.execute("BEGIN")

        goods_stats = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active,
                SUM(CASE WHEN status = 'archived' THEN 1 ELSE 0 END) AS archived,
                SUM(CASE WHEN is_photo = 1 THEN 1 ELSE 0 END) AS photos,
                SUM(CASE WHEN described = 1 THEN 1 ELSE 0 END) AS described,
                COALESCE(SUM(weight), 0) AS mass
            FROM (
                SELECT
                    status,
                    weight,
                    CASE
                        WHEN photo_filename IS NOT NULL
                             AND photo_filename <> '' THEN 1
                        ELSE 0
                    END AS is_photo,
                    CASE
                        WHEN description IS NOT NULL
                             AND trim(description) <> '' THEN 1
                        ELSE 0
                    END AS described
                FROM goods
            )
            """
        ).fetchone()

        category_rows = connection.execute(
            """
            SELECT
                categories.name,
                COUNT(goods.id) AS goods_count,
                SUM(CASE WHEN goods.status = 'archived' THEN 1 ELSE 0 END)
                    AS archived_count
            FROM categories
            LEFT JOIN goods ON goods.category_id = categories.id
            GROUP BY categories.id, categories.name
            ORDER BY goods_count DESC, categories.name ASC
            """
        ).fetchall()

        action_rows = connection.execute(
            """
            SELECT action, COUNT(*) AS total
            FROM audit_log
            WHERE entity_type = 'goods'
            GROUP BY action
            """
        ).fetchall()

        event_totals = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS last_24h,
                MAX(created_at) AS latest
            FROM audit_log
            WHERE entity_type = 'goods'
            """,
            (horizon,),
        ).fetchone()

        deleted_retained = connection.execute(
            """
            SELECT COUNT(DISTINCT entity_id) AS total
            FROM audit_log
            WHERE entity_type = 'goods' AND action = 'deleted'
            """
        ).fetchone()["total"]

        daily_rows = connection.execute(
            """
            SELECT substr(created_at, 1, 10) AS day, action, COUNT(*) AS total
            FROM audit_log
            WHERE entity_type = 'goods' AND created_at >= ?
            GROUP BY day, action
            """,
            (window_start,),
        ).fetchall()

        recent_rows = connection.execute(
            """
            SELECT id, entity_id, entity_label, action, created_at
            FROM audit_log
            WHERE entity_type = 'goods'
            ORDER BY id DESC
            LIMIT 12
            """
        ).fetchall()

    counts = dict(goods_stats)
    total = counts["total"] or 0
    active = counts["active"] or 0
    archived = counts["archived"] or 0
    photos = counts["photos"] or 0
    described = counts["described"] or 0
    mass = float(counts["mass"] or 0)

    actions = {row["action"]: row["total"] for row in action_rows}
    for action in ACTIONS:
        actions.setdefault(action, 0)

    # -- daily matrix -------------------------------------------------
    per_day = {}
    for row in daily_rows:
        bucket = per_day.setdefault(
            row["day"],
            {action: 0 for action in ACTIONS},
        )
        if row["action"] in bucket:
            bucket[row["action"]] = row["total"]

    daily = []
    for day in window:
        info = per_day.get(day, {action: 0 for action in ACTIONS})
        daily.append({
            "day": day,
            "label": day[8:],
            "created": info.get("created", 0),
            "archived": info.get("archived", 0),
            "restored": info.get("restored", 0),
            "deleted": info.get("deleted", 0),
            "total": sum(info.values()),
        })

    peak_day = max(daily, key=lambda row: row["total"], default=None)
    window_total = sum(row["total"] for row in daily)

    categories = [
        {
            "name": row["name"],
            "goods_count": row["goods_count"] or 0,
            "archived_count": row["archived_count"] or 0,
        }
        for row in category_rows
    ]
    used_categories = [row for row in categories if row["goods_count"] > 0]

    latest = event_totals["latest"]
    if latest:
        try:
            latest_dt = datetime.strptime(latest, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
            latest_human = latest_dt.strftime("%d %b %Y · %H:%M UTC")
        except ValueError:
            latest_human = latest
    else:
        latest_human = "no events yet"

    return {
        "counts": {
            "goods_total": total,
            "active": active,
            "archived": archived,
            "categories": len(categories),
            "categories_used": len(used_categories),
            "photos": photos,
            "without_photo": total - photos,
            "described": described,
            "events_total": event_totals["total"] or 0,
            "events_24h": event_totals["last_24h"] or 0,
            "deleted_retained": deleted_retained,
        },
        "ratios": {
            "active_pct": _pct(active, total),
            "archived_pct": _pct(archived, total),
            "photo_pct": _pct(photos, total),
            "described_pct": _pct(described, total),
            "catalogue_pct": _pct(len(used_categories), len(categories)),
        },
        "mass": {
            "total_kg": round(mass, 3),
            "avg_kg": round(mass / total, 3) if total else 0,
        },
        "actions": actions,
        "lifecycle": {
            "registered": actions.get("created", 0),
            "active": active,
            "archived": archived,
            "purged": actions.get("deleted", 0),
            "retained": deleted_retained,
        },
        "pipeline": {
            "received": total,
            "catalogued": total,
            "described": described,
            "captured": photos,
            "archived": archived,
        },
        "daily": daily,
        "window": {
            "days": days,
            "events": window_total,
            "peak_day": peak_day,
            "busiest": peak_day["label"] if peak_day and peak_day["total"] else "—",
        },
        "categories": categories,
        "recent": [
            {
                "id": row["id"],
                "entity_id": row["entity_id"],
                "entity_label": row["entity_label"],
                "action": row["action"],
                "word": ACTION_WORDS.get(row["action"], row["action"]),
                "created_at": row["created_at"],
            }
            for row in recent_rows
        ],
        "latest_event": latest_human,
    }


def get_live_metrics():
    """Small payload polled by the dashboard for the 'live' feel."""
    snapshot = get_ops_snapshot(days=7)
    counts = snapshot["counts"]

    return {
        "total_goods": counts["goods_total"],
        "active_goods": counts["active"],
        "archived_goods": counts["archived"],
        "categories": counts["categories"],
        "photos": counts["photos"],
        "without_photo": counts["without_photo"],
        "events_total": counts["events_total"],
        "events_24h": counts["events_24h"],
        "retained": counts["deleted_retained"],
        "avg_kg": snapshot["mass"]["avg_kg"],
        "window_events": snapshot["window"]["events"],
        "latest": snapshot["latest_event"],
        "updated_at": datetime.now(timezone.utc).strftime("%H:%M:%S"),
    }


if __name__ == "__main__":
    data = get_ops_snapshot()
    print("GoodsHub operations snapshot")
    print("---------------------------")
    for key, value in data["counts"].items():
        print(f"{key:>18}: {value}")
    print("\nLifecycle:", data["lifecycle"])
    print("Pipeline:", data["pipeline"])
    print("\nActivity matrix:")
    for row in data["daily"]:
        print(f"  {row['day']}  +{row['created']}  ~{row['updated']}"
              f"  A{row['archived']}  R{row['restored']}  D{row['deleted']}")
    print("\nLatest event:", data["latest_event"])
