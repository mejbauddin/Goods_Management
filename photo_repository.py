"""Goods photo filenames stored in the database.

Improvements over the original version:
  * Reuses the shared write-transaction, audit-log and column-check
    helpers instead of repeating that code.
  * Filenames are validated before they are saved, so a bad value can
    never be stored (and later used to build a file path). Only names made
    by the upload code ("<32 hex characters>.jpg") or an empty string are
    accepted.
  * New remove_goods_photo(), which returns the old filename so the caller
    can delete the file from disk.
  * New get_photo_filenames() lists every filename in use, so unused files
    in the photo folder can be found and cleaned up.

Existing behaviour is unchanged: initialize_photo_column() and
update_goods_photo(goods_id, filename) keep their names and return values.
"""

import re
from contextlib import closing

from database import column_exists, get_connection, initialize_database

# These helpers are shared inside the package (see goods_repository.py).
from goods_repository import _get_row, _write_audit, _write_transaction

# Same pattern that app.py uses when serving /goods/photos/<filename>.
PHOTO_FILENAME_PATTERN = re.compile(r"[0-9a-f]{32}\.jpg")


def _clean_filename(filename):
    """Return a safe filename, or '' for "no photo". Raise ValueError
    for anything else."""
    if filename is None:
        return ""

    if not isinstance(filename, str):
        raise ValueError("Invalid photo filename.")

    if filename == "":
        return ""

    if not PHOTO_FILENAME_PATTERN.fullmatch(filename):
        raise ValueError("Invalid photo filename.")

    return filename


def initialize_photo_column():
    """Add photo storage support if it is not already present.

    Returns True if the column was added, False if it already existed.
    """
    with _write_transaction() as connection:
        if column_exists(connection, "goods", "photo_filename"):
            return False

        connection.execute(
            """
            ALTER TABLE goods
            ADD COLUMN photo_filename TEXT NOT NULL DEFAULT ''
            """
        )

    return True


def _set_photo(goods_id, filename, action):
    """Save a photo filename and record the change.

    Returns (changed, old_filename).
    """
    filename = _clean_filename(filename)

    with _write_transaction() as connection:
        old_record = _get_row(connection, goods_id)

        if old_record is None:
            raise ValueError("Goods record not found.")

        old_filename = old_record["photo_filename"]

        if old_filename == filename:
            return False, old_filename

        connection.execute(
            """
            UPDATE goods
            SET photo_filename = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (filename, goods_id),
        )

        _write_audit(
            connection,
            goods_id,
            old_record["code"],
            action,
            old_record,
            _get_row(connection, goods_id),
        )

    return True, old_filename


def update_goods_photo(goods_id, filename):
    """Save a photo filename and record the change.

    Returns True if the photo changed, False if it was already set.
    """
    changed, _old = _set_photo(goods_id, filename, "photo_updated")
    return changed


def replace_goods_photo(goods_id, filename):
    """Like update_goods_photo(), but returns the previous filename
    ('' if there was none, or None if nothing changed) so the caller can
    delete the old file from disk after a successful save."""
    changed, old_filename = _set_photo(goods_id, filename, "photo_updated")
    return old_filename if changed else None


def remove_goods_photo(goods_id):
    """Clear the photo. Returns the removed filename, or None if the
    goods had no photo."""
    changed, old_filename = _set_photo(goods_id, "", "photo_removed")
    return old_filename if changed else None


def get_photo_filenames():
    """Return the set of photo filenames currently used by goods.

    Compare it with the files in the photo folder to find unused files.
    """
    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT photo_filename FROM goods WHERE photo_filename != ''"
        ).fetchall()

    return {row["photo_filename"] for row in rows}


if __name__ == "__main__":
    initialize_database()

    if initialize_photo_column():
        print("Photo column added successfully.")
    else:
        print("Photo column already exists.")

    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT id, code, photo_filename FROM goods ORDER BY id"
        ).fetchall()

    for row in rows:
        print(
            f"{row['id']} | {row['code']} | "
            f"Photo: {row['photo_filename'] or '(none)'}"
        )

    print(f"\nGoods with a photo: {len(get_photo_filenames())}")
