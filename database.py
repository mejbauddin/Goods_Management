"""SQLite connection and schema for GoodsHub.

Improvements over the original version:
  * Connections wait up to 10 s when the database is busy instead of
    failing immediately with "database is locked".
  * WAL journal mode (set once in initialize_database): readers no longer
    block writers, which suits a web app serving several requests.
  * More indexes for the queries the app actually runs (newest goods,
    audit-log lookups, status + category filters).
  * `connect()` context manager: commits on success, rolls back on error
    and always closes the connection.
  * `backup_database()` makes a safe copy of the live database and
    `column_exists()` helps with small schema upgrades.
  * The database file can be moved with the GOODSHUB_DB environment
    variable (useful for tests).

The schema and the existing names (BASE_DIR, DATA_DIR, DATABASE_PATH,
get_connection, initialize_database) are unchanged, so no other file
needs to change and existing data stays valid.
"""

import os
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path


# Keep the database path independent of where we run the command.
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "instance"
DATABASE_PATH = Path(
    os.environ.get("GOODSHUB_DB", DATA_DIR / "goodshub.sqlite3")
)
BACKUP_DIR = DATA_DIR / "backups"

BUSY_TIMEOUT_SECONDS = 10


def get_connection():
    """Open a connection to our SQLite database."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH, timeout=BUSY_TIMEOUT_SECONDS)

    # Access columns by name, for example: record["name"].
    connection.row_factory = sqlite3.Row

    # Enforce relationships between tables.
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


@contextmanager
def connect():
    """Open a connection that commits on success and rolls back on error.

    Usage:
        with connect() as connection:
            connection.execute(...)
    """
    connection = get_connection()

    try:
        with connection:
            yield connection
    finally:
        connection.close()


def column_exists(connection, table, column):
    """True if `table` already has `column` (for ALTER TABLE upgrades)."""
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def initialize_database():
    """Create our tables if they do not already exist."""
    connection = get_connection()

    try:
        # Persistent setting stored in the database file; must be changed
        # outside a transaction.
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")

        with connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    name TEXT NOT NULL COLLATE NOCASE UNIQUE
                        CHECK(length(trim(name)) BETWEEN 1 AND 60)
                );

                CREATE TABLE IF NOT EXISTS goods (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    code TEXT NOT NULL COLLATE NOCASE UNIQUE
                        CHECK(length(code) BETWEEN 2 AND 30),

                    name TEXT NOT NULL
                        CHECK(length(trim(name)) BETWEEN 1 AND 120),

                    category_id INTEGER NOT NULL,

                    unit TEXT NOT NULL
                        CHECK(unit IN (
                            'Piece', 'Box', 'Pack', 'Bag',
                            'Bottle', 'Set', 'Roll'
                        )),

                    weight REAL NOT NULL
                        CHECK(weight > 0 AND weight <= 1000000),

                    description TEXT NOT NULL DEFAULT ''
                        CHECK(length(description) <= 2000),

                    status TEXT NOT NULL DEFAULT 'active'
                        CHECK(status IN ('active', 'archived')),

                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (category_id)
                        REFERENCES categories(id)
                        ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    entity_type TEXT NOT NULL
                        CHECK(entity_type IN ('goods', 'category')),

                    entity_id INTEGER NOT NULL,

                    entity_label TEXT NOT NULL,

                    action TEXT NOT NULL,

                    before_json TEXT,

                    after_json TEXT,

                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_goods_category
                    ON goods(category_id);

                CREATE INDEX IF NOT EXISTS idx_goods_status
                    ON goods(status);

                -- Dashboard: newest goods first.
                CREATE INDEX IF NOT EXISTS idx_goods_created
                    ON goods(created_at DESC, id DESC);

                -- Goods list filtered by status and category.
                CREATE INDEX IF NOT EXISTS idx_goods_status_category
                    ON goods(status, category_id);

                -- History page and deleted-goods lookups.
                CREATE INDEX IF NOT EXISTS idx_audit_entity
                    ON audit_log(entity_type, entity_id, id);

                CREATE INDEX IF NOT EXISTS idx_audit_action
                    ON audit_log(entity_type, action, id);
            """)
    finally:
        connection.close()


def backup_database(destination=None, keep=10):
    """Copy the live database to a new file and return its path.

    Uses SQLite's online backup, so it is safe while the app is running.
    Only the newest `keep` automatic backups are kept (older ones are
    deleted); pass keep=None to disable cleanup.
    """
    if destination is None:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        destination = BACKUP_DIR / f"goodshub_{stamp}.sqlite3"
        automatic = True
    else:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        automatic = False

    with closing(get_connection()) as source, \
            closing(sqlite3.connect(destination)) as target:
        source.backup(target)

    if automatic and keep:
        old_backups = sorted(BACKUP_DIR.glob("goodshub_*.sqlite3"))[:-keep]
        for old in old_backups:
            old.unlink(missing_ok=True)

    return destination


def check_database():
    """Return (ok, message) from SQLite's integrity and key checks."""
    with closing(get_connection()) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        broken_keys = connection.execute("PRAGMA foreign_key_check").fetchall()

    if integrity != "ok":
        return False, f"Integrity check failed: {integrity}"

    if broken_keys:
        return False, f"{len(broken_keys)} foreign key problem(s) found."

    return True, "Database is healthy."


if __name__ == "__main__":
    initialize_database()

    print("Database initialized successfully.")
    print(f"Database location: {DATABASE_PATH}")
    print(check_database()[1])
