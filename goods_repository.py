"""Goods storage with audit history.

Improvements over the original version:
  * The validation block that was copy-pasted into add_goods() and
    update_goods() is now one function, and the audit-log INSERT that was
    repeated five times is one helper.
  * One transaction helper: every write runs with BEGIN IMMEDIATE, so the
    checks and the save cannot race another writer (add_goods did not do
    this before).
  * update_goods() skips the save and the history entry when nothing
    changed, and returns True/False (it used to return None).
  * get_all_goods() can also filter by category, sort, and paginate, and
    count_goods() returns the matching total for page numbers.
  * Text inputs that are not strings give a clear error instead of an
    AttributeError.

Existing names, arguments and error messages are unchanged, so app.py,
csv_import_service.py and the templates keep working.
"""

import json
import math
import sqlite3
from contextlib import closing, contextmanager

from database import get_connection, initialize_database


ALLOWED_UNITS = (
    "Piece", "Box", "Pack", "Bag",
    "Bottle", "Set", "Roll"
)

STATUS_FILTERS = ("all", "active", "archived")

MAX_WEIGHT = 1_000_000
MAX_DESCRIPTION_LENGTH = 2000

# Whitelist for ORDER BY (column names can never come from user input).
SORT_COLUMNS = {
    "id": "goods.id",
    "code": "goods.code",
    "name": "goods.name",
    "category": "categories.name",
    "weight": "goods.weight",
    "created": "goods.created_at",
    "updated": "goods.updated_at",
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _text(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")

    return value.strip()


def _validate_goods(code, name, unit, weight, description):
    """Check and clean the user's input; return the cleaned values."""
    code = _text(code, "Goods code").upper()
    name = _text(name, "Goods name")
    unit = _text(unit, "Unit")
    description = _text(description, "Description")

    if not 2 <= len(code) <= 30:
        raise ValueError("Goods code must contain 2–30 characters.")

    if not 1 <= len(name) <= 120:
        raise ValueError("Goods name must contain 1–120 characters.")

    if unit not in ALLOWED_UNITS:
        raise ValueError("Please select a valid unit.")

    try:
        weight = float(weight)
    except (TypeError, ValueError):
        raise ValueError("Weight must be a number.") from None

    if not math.isfinite(weight) or not 0 < weight <= MAX_WEIGHT:
        raise ValueError(
            "Weight must be greater than 0 and at most 1,000,000 kg."
        )

    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ValueError("Description cannot exceed 2,000 characters.")

    return code, name, unit, weight, description


@contextmanager
def _write_transaction():
    """Open a connection with a write lock; commit on success, roll back
    on any error, and always close."""
    with closing(get_connection()) as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            yield connection


def _write_audit(connection, goods_id, label, action, before, after):
    """Add one goods event to the audit log (inside the caller's
    transaction). `before` and `after` are sqlite rows, dicts or None."""
    def to_json(record):
        return None if record is None else json.dumps(
            dict(record), ensure_ascii=False
        )

    connection.execute(
        """
        INSERT INTO audit_log (
            entity_type,
            entity_id,
            entity_label,
            action,
            before_json,
            after_json
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("goods", goods_id, label, action, to_json(before), to_json(after)),
    )


def _get_row(connection, goods_id):
    return connection.execute(
        "SELECT * FROM goods WHERE id = ?", (goods_id,)
    ).fetchone()


def _require_category(connection, category_id):
    category = connection.execute(
        "SELECT id FROM categories WHERE id = ?", (category_id,)
    ).fetchone()

    if category is None:
        raise ValueError("The selected category does not exist.")

    return category["id"]


def _is_duplicate_code(error):
    return "UNIQUE constraint failed: goods.code" in str(error)


# --------------------------------------------------------------------------
# Create, read, update
# --------------------------------------------------------------------------

def add_goods(code, name, category_id, unit, weight, description=""):
    """Check and save a goods record together with its history."""
    code, name, unit, weight, description = _validate_goods(
        code, name, unit, weight, description
    )

    try:
        # Save the goods and history together.
        with _write_transaction() as connection:
            category_id = _require_category(connection, category_id)

            cursor = connection.execute(
                """
                INSERT INTO goods (
                    code, name, category_id, unit, weight, description
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (code, name, category_id, unit, weight, description),
            )
            goods_id = cursor.lastrowid

            _write_audit(
                connection, goods_id, code, "created",
                None, _get_row(connection, goods_id),
            )

        return goods_id

    except sqlite3.IntegrityError as error:
        if _is_duplicate_code(error):
            raise ValueError(
                f"The goods code '{code}' already exists."
            ) from error

        raise


def _build_filters(search, status, category_id):
    """Return the WHERE clause and its parameters for the goods list."""
    if status not in STATUS_FILTERS:
        raise ValueError("Invalid status filter.")

    conditions = []
    parameters = []

    search = (search or "").strip()

    if search:
        conditions.append("""
            (
                instr(lower(goods.code), lower(?)) > 0
                OR instr(lower(goods.name), lower(?)) > 0
            )
        """)
        parameters.extend([search, search])

    if status != "all":
        conditions.append("goods.status = ?")
        parameters.append(status)

    if category_id is not None:
        conditions.append("goods.category_id = ?")
        parameters.append(category_id)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    return where, parameters


def get_all_goods(
    search="",
    status="all",
    *,
    category_id=None,
    sort="id",
    descending=False,
    limit=None,
    offset=0,
):
    """Find goods by code/name; optionally filter, sort and paginate.

    Called as get_all_goods(search, status) it behaves exactly as before.
    """
    where, parameters = _build_filters(search, status, category_id)

    if sort not in SORT_COLUMNS:
        raise ValueError("Invalid sort column.")

    direction = "DESC" if descending else "ASC"

    query = f"""
        SELECT
            goods.*,
            categories.name AS category_name
        FROM goods
        JOIN categories ON goods.category_id = categories.id
        {where}
        ORDER BY {SORT_COLUMNS[sort]} {direction}, goods.id ASC
    """

    if limit is not None:
        query += " LIMIT ? OFFSET ?"
        parameters.extend([max(0, int(limit)), max(0, int(offset))])

    with closing(get_connection()) as connection:
        rows = connection.execute(query, parameters).fetchall()

    return [dict(row) for row in rows]


def count_goods(search="", status="all", *, category_id=None):
    """Count the goods that get_all_goods() would return (for paging)."""
    where, parameters = _build_filters(search, status, category_id)

    with closing(get_connection()) as connection:
        return connection.execute(
            f"SELECT COUNT(*) FROM goods {where}", parameters
        ).fetchone()[0]


def get_goods_by_id(goods_id):
    """Find one goods record using its permanent ID."""
    with closing(get_connection()) as connection:
        row = _get_row(connection, goods_id)

    return dict(row) if row is not None else None


def update_goods(
    goods_id,
    code,
    name,
    category_id,
    unit,
    weight,
    description=""
):
    """Update a goods record and save its before/after history.

    Returns True if something changed, or False if the new values are the
    same as the saved ones (nothing is written in that case).
    """
    code, name, unit, weight, description = _validate_goods(
        code, name, unit, weight, description
    )

    try:
        with _write_transaction() as connection:
            # The transaction already started, so these reads are stable.
            old_record = _get_row(connection, goods_id)

            if old_record is None:
                raise ValueError("Goods record not found.")

            category_id = _require_category(connection, category_id)

            unchanged = (
                old_record["code"] == code
                and old_record["name"] == name
                and old_record["category_id"] == category_id
                and old_record["unit"] == unit
                and old_record["weight"] == weight
                and old_record["description"] == description
            )

            if unchanged:
                return False

            connection.execute(
                """
                UPDATE goods
                SET code = ?,
                    name = ?,
                    category_id = ?,
                    unit = ?,
                    weight = ?,
                    description = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (code, name, category_id, unit, weight, description,
                 goods_id),
            )

            _write_audit(
                connection, goods_id, code, "updated",
                old_record, _get_row(connection, goods_id),
            )

        return True

    except sqlite3.IntegrityError as error:
        if _is_duplicate_code(error):
            raise ValueError(
                f"The goods code '{code}' already exists."
            ) from error

        raise


# --------------------------------------------------------------------------
# Archive, restore, delete
# --------------------------------------------------------------------------

def set_goods_status(goods_id, new_status):
    """Archive or restore goods and record the change."""
    if new_status not in ("active", "archived"):
        raise ValueError("Invalid goods status.")

    with _write_transaction() as connection:
        old_record = _get_row(connection, goods_id)

        if old_record is None:
            raise ValueError("Goods record not found.")

        # Avoid adding history when nothing has changed.
        if old_record["status"] == new_status:
            return False

        connection.execute(
            """
            UPDATE goods
            SET status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_status, goods_id),
        )

        _write_audit(
            connection,
            goods_id,
            old_record["code"],
            "archived" if new_status == "archived" else "restored",
            old_record,
            _get_row(connection, goods_id),
        )

    return True


def delete_goods(goods_id):
    """Permanently delete archived goods and retain their history."""
    with _write_transaction() as connection:
        item = _get_row(connection, goods_id)

        if item is None:
            raise ValueError("Goods record not found.")

        if item["status"] != "archived":
            raise ValueError(
                "Archive this goods record before permanently deleting it."
            )

        connection.execute("DELETE FROM goods WHERE id = ?", (goods_id,))

        _write_audit(
            connection, goods_id, item["code"], "deleted", item, None
        )

    return True


# Run this section only when executing this file directly.
if __name__ == "__main__":
    from category_repository import get_all_categories

    initialize_database()

    categories = get_all_categories()

    electronics = next(
        (
            category
            for category in categories
            if category["name"].casefold() == "electronics"
        ),
        None
    )

    if electronics is None:
        print("Please create the Electronics category first.")

    else:
        try:
            goods_id = add_goods(
                code="EL-001",
                name="Wireless keyboard",
                category_id=electronics["id"],
                unit="Piece",
                weight=0.65,
                description="Wireless keyboard with USB receiver."
            )

            print(f"Goods added successfully. ID: {goods_id}")

        except ValueError as error:
            print(f"Not added: {error}")

    print("\nSaved goods:")

    for item in get_all_goods():
        print(
            f"{item['id']} | "
            f"{item['code']} | "
            f"{item['name']} | "
            f"{item['category_name']} | "
            f"{item['weight']} kg"
        )
