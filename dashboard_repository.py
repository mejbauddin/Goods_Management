"""Dashboard summary data.

Reads a single consistent snapshot of the database and returns everything
the dashboard page needs: summary counts, chart data, top categories,
unused categories, goods added per month, recent goods, and recent activity.

Notes
-----
* `connection.row_factory` is expected to be `sqlite3.Row`
  (`database.get_connection()` sets this; do not change it).
* `last_months()` and the `monthly` chart assume `created_at` is stored as
  ISO-8601 UTC text (`YYYY-MM-DD HH:MM:SS`). If that ever changes, the
  month buckets here must change too.
"""

from contextlib import closing
from datetime import datetime, timezone

from database import get_connection


def last_months(count):
    """Return the last `count` months as 'YYYY-MM', oldest first."""
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month
    months = []

    for _ in range(count):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month, year = 12, year - 1

    return months[::-1]


def _percent(part, whole):
    return round(part * 100 / whole, 1) if whole else 0


def _safe_int(value, default, minimum=1):
    """Coerce `value` to int, falling back to `default` on any problem."""
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, result)


def get_dashboard_data(recent_limit=5, months=6):
    """Read summary counts, chart data and the newest goods records."""
    recent_limit = _safe_int(recent_limit, 5)
    months = _safe_int(months, 6)

    with closing(get_connection()) as connection:
        # Read every number from one consistent snapshot.
        connection.execute("BEGIN")

        summary = connection.execute(
            """
            SELECT
                COUNT(*) AS total_goods,
                COALESCE(SUM(CASE WHEN status = 'active'   THEN 1 ELSE 0 END), 0) AS active_goods,
                COALESCE(SUM(CASE WHEN status = 'archived' THEN 1 ELSE 0 END), 0) AS archived_goods,
                COALESCE(
                    SUM(CASE WHEN photo_filename IS NULL OR photo_filename = ''
                             THEN 1 ELSE 0 END),
                    0
                ) AS without_photo
            FROM goods
            """
        ).fetchone()

        # One row per category (including unused ones, count = 0).
        category_rows = connection.execute(
            """
            SELECT
                categories.name,
                COUNT(goods.id) AS goods_count
            FROM categories
            LEFT JOIN goods ON goods.category_id = categories.id
            GROUP BY categories.id, categories.name
            ORDER BY goods_count DESC, categories.name ASC
            """
        ).fetchall()

        recent_rows = connection.execute(
            """
            SELECT
                goods.id,
                goods.code,
                goods.name,
                goods.photo_filename,
                goods.status,
                goods.created_at,
                categories.name AS category_name
            FROM goods
            JOIN categories ON goods.category_id = categories.id
            ORDER BY goods.created_at DESC, goods.id DESC
            LIMIT ?
            """,
            (recent_limit,),
        ).fetchall()

        month_keys = last_months(months)

        # Index-friendly: compare a *stored* column prefix to a literal.
        # `substr(created_at, 1, 7)` is a plain function on a literal, so
        # SQLite can still scan the created_at index range.
        monthly_rows = connection.execute(
            """
            SELECT substr(created_at, 1, 7) AS month, COUNT(*) AS total
            FROM goods
            WHERE created_at >= ? || '-01 00:00:00'
            GROUP BY month
            """,
            (month_keys[0],),
        ).fetchall()

        activity_rows = connection.execute(
            """
            SELECT id, entity_id, entity_label, action, created_at
            FROM audit_log
            WHERE entity_type = 'goods'
            ORDER BY id DESC
            LIMIT ?
            """,
            (recent_limit,),
        ).fetchall()

    total = summary["total_goods"]
    per_month = {row["month"]: row["total"] for row in monthly_rows}
    category_counts = [dict(row) for row in category_rows]

    return {
        # Original keys.
        "total_goods": total,
        "active_goods": summary["active_goods"],
        "archived_goods": summary["archived_goods"],
        "total_categories": len(category_counts),
        "recent_goods": [dict(row) for row in recent_rows],
        # New keys.
        "active_percent": _percent(summary["active_goods"], total),
        "archived_percent": _percent(summary["archived_goods"], total),
        "without_photo": summary["without_photo"],
        "top_categories": [
            row for row in category_counts if row["goods_count"] > 0
        ][:5],
        "unused_categories": [
            row["name"] for row in category_counts if row["goods_count"] == 0
        ],
        "monthly": [
            {"month": key, "count": per_month.get(key, 0)}
            for key in month_keys
        ],
        "recent_activity": [dict(row) for row in activity_rows],
    }


if __name__ == "__main__":
    data = get_dashboard_data()

    print("GoodsHub dashboard")
    print("------------------")
    print(f"Total goods records: {data['total_goods']}")
    print(
        f"Active goods: {data['active_goods']} "
        f"({data['active_percent']}%)"
    )
    print(
        f"Archived goods: {data['archived_goods']} "
        f"({data['archived_percent']}%)"
    )
    print(f"Categories: {data['total_categories']}")
    print(f"Goods without a photo: {data['without_photo']}")

    print("\nTop categories:")
    for row in data["top_categories"]:
        print(f"  {row['name']}: {row['goods_count']}")

    if data["unused_categories"]:
        print("\nUnused categories: " + ", ".join(data["unused_categories"]))

    print("\nGoods added per month:")
    for row in data["monthly"]:
        print(f"  {row['month']}: {row['count']}")

    print("\nRecently registered goods:")
    for item in data["recent_goods"]:
        print(
            f"{item['code']} | "
            f"{item['name']} | "
            f"{item['category_name']} | "
            f"{item['status']}"
        )

    print("\nRecent activity:")
    for event in data["recent_activity"]:
        print(
            f"  {event['created_at']} | "
            f"{event['action']} | {event['entity_label']}"
        )