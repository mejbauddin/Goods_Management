"""Category storage with audit history.

Improvements over the original version:
  * One shared validator (`_clean_name`) instead of two copies.
  * One shared `_write_audit()` and one shared duplicate-name handler.
  * Duplicate names are detected case-insensitively ("Office" vs "office")
    and extra inner spaces are collapsed ("Office   Supplies").
  * All write operations use the same transaction pattern
    (BEGIN IMMEDIATE), so concurrent writers cannot race the checks.
  * New helpers: get_category_by_id() and get_all_categories(with_counts=True)
    for showing how many goods use each category.

The public functions keep their original names and return values:
  add_category, get_all_categories, rename_category, delete_category.
"""

import json
import re
import sqlite3
from contextlib import closing

from database import get_connection, initialize_database

MAX_NAME_LENGTH = 60


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _clean_name(name):
    """Validate a category name and return it with tidy spacing."""
    if not isinstance(name, str):
        raise ValueError("Category name must be text.")

    # Trim and collapse runs of whitespace into single spaces.
    name = re.sub(r"\s+", " ", name).strip()

    if not name:
        raise ValueError("Category name cannot be empty.")

    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(
            f"Category name cannot exceed {MAX_NAME_LENGTH} characters."
        )

    return name


def _write_audit(connection, category_id, label, action, before, after):
    """Add one category event to the audit log (inside the caller's
    transaction)."""
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
        (
            "category",
            category_id,
            label,
            action,
            None if before is None else json.dumps(before, ensure_ascii=False),
            None if after is None else json.dumps(after, ensure_ascii=False),
        ),
    )


def _ensure_name_is_free(connection, name, ignore_id=None):
    """Raise ValueError if another category already uses this name
    (case-insensitive)."""
    row = connection.execute(
        """
        SELECT id
        FROM categories
        WHERE name = ? COLLATE NOCASE
          AND id IS NOT ?
        """,
        (name, ignore_id),
    ).fetchone()

    if row is not None:
        raise ValueError(f"The category '{name}' already exists.")


def _is_duplicate_name_error(error):
    return "UNIQUE constraint failed: categories.name" in str(error)


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def add_category(name):
    """Validate and save a category, together with its history."""
    name = _clean_name(name)

    with closing(get_connection()) as connection:
        try:
            # Save the category and its history as one transaction.
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                _ensure_name_is_free(connection, name)

                cursor = connection.execute(
                    "INSERT INTO categories (name) VALUES (?)",
                    (name,),
                )
                category_id = cursor.lastrowid

                _write_audit(
                    connection,
                    category_id,
                    name,
                    "created",
                    None,
                    {"id": category_id, "name": name},
                )

            return category_id

        except sqlite3.IntegrityError as error:
            if _is_duplicate_name_error(error):
                raise ValueError(
                    f"The category '{name}' already exists."
                ) from error

            raise


def get_all_categories(with_counts=False):
    """Return categories in ID order.

    With with_counts=True each row also has "goods_count" (archived goods
    included), which is handy for the categories page and charts.
    """
    if with_counts:
        query = """
            SELECT
                categories.id,
                categories.name,
                COUNT(goods.id) AS goods_count
            FROM categories
            LEFT JOIN goods ON goods.category_id = categories.id
            GROUP BY categories.id, categories.name
            ORDER BY categories.id ASC
        """
    else:
        query = """
            SELECT id, name
            FROM categories
            ORDER BY id ASC
        """

    with closing(get_connection()) as connection:
        rows = connection.execute(query).fetchall()

    return [dict(row) for row in rows]


def get_category_by_id(category_id):
    """Return one category as a dict, or None if it does not exist."""
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT id, name FROM categories WHERE id = ?",
            (category_id,),
        ).fetchone()

    return dict(row) if row else None


def rename_category(category_id, new_name):
    """Rename a category and record the old and new names.

    Returns True if the name changed, False if it was already that name.
    """
    new_name = _clean_name(new_name)

    with closing(get_connection()) as connection:
        try:
            with connection:
                connection.execute("BEGIN IMMEDIATE")

                old_record = connection.execute(
                    "SELECT id, name FROM categories WHERE id = ?",
                    (category_id,),
                ).fetchone()

                if old_record is None:
                    raise ValueError("Category not found.")

                if old_record["name"] == new_name:
                    return False

                # Allows changing only the capitalisation of the same
                # category, but blocks a clash with a different one.
                _ensure_name_is_free(
                    connection, new_name, ignore_id=category_id
                )

                connection.execute(
                    "UPDATE categories SET name = ? WHERE id = ?",
                    (new_name, category_id),
                )

                _write_audit(
                    connection,
                    category_id,
                    new_name,
                    "renamed",
                    dict(old_record),
                    {"id": category_id, "name": new_name},
                )

            return True

        except sqlite3.IntegrityError as error:
            if _is_duplicate_name_error(error):
                raise ValueError(
                    f"The category '{new_name}' already exists."
                ) from error

            raise


def delete_category(category_id):
    """Delete an unused category and preserve its history."""
    with closing(get_connection()) as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")

            category = connection.execute(
                "SELECT id, name FROM categories WHERE id = ?",
                (category_id,),
            ).fetchone()

            if category is None:
                raise ValueError("Category not found.")

            goods_count = connection.execute(
                "SELECT COUNT(*) FROM goods WHERE category_id = ?",
                (category_id,),
            ).fetchone()[0]

            if goods_count > 0:
                raise ValueError(
                    "Cannot delete this category because "
                    f"{goods_count} goods record(s) use it. "
                    "This includes archived goods."
                )

            connection.execute(
                "DELETE FROM categories WHERE id = ?",
                (category_id,),
            )

            _write_audit(
                connection,
                category_id,
                category["name"],
                "deleted",
                dict(category),
                None,
            )

    return True


# This section runs only when we execute this file directly.
if __name__ == "__main__":
    initialize_database()

    print("Adding example categories...")

    for category_name in ("Electronics", "Office Supplies", "Packaging"):
        try:
            new_id = add_category(category_name)
            print(f"Added: {category_name} (ID: {new_id})")

        except ValueError as error:
            print(f"Not added: {error}")

    print("\nSaved categories:")

    for category in get_all_categories(with_counts=True):
        print(
            f"{category['id']} - {category['name']} "
            f"({category['goods_count']} goods)"
        )
