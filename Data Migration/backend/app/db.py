from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / ".data"
DB_PATH = DATA_DIR / "app.db"


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS postgres_instances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('source', 'target', 'both')),
                host TEXT NOT NULL,
                port INTEGER NOT NULL,
                database_name TEXT NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                sslmode TEXT NOT NULL DEFAULT 'prefer',
                proxy_type TEXT,
                proxy_host TEXT,
                proxy_port INTEGER,
                proxy_username TEXT,
                proxy_password TEXT,
                description TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        ensure_columns(
            conn,
            "postgres_instances",
            {
                "proxy_type": "TEXT",
                "proxy_host": "TEXT",
                "proxy_port": "INTEGER",
                "proxy_username": "TEXT",
                "proxy_password": "TEXT",
            },
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_postgres_instances_updated_at
            AFTER UPDATE ON postgres_instances
            BEGIN
                UPDATE postgres_instances
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = NEW.id;
            END
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS migration_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                source_instance_id INTEGER NOT NULL,
                target_instance_id INTEGER NOT NULL,
                schemas_json TEXT,
                tables_json TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                description TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(source_instance_id) REFERENCES postgres_instances(id),
                FOREIGN KEY(target_instance_id) REFERENCES postgres_instances(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_migration_tasks_updated_at
            AFTER UPDATE ON migration_tasks
            BEGIN
                UPDATE migration_tasks
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = NEW.id;
            END
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                operation TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                details_json TEXT,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT,
                FOREIGN KEY(task_id) REFERENCES migration_tasks(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sequence_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                operation TEXT NOT NULL,
                sequence_schema TEXT NOT NULL,
                sequence_name TEXT NOT NULL,
                table_schema TEXT,
                table_name TEXT,
                column_name TEXT,
                source_last_value INTEGER,
                target_current_value INTEGER,
                target_value INTEGER,
                should_apply INTEGER NOT NULL DEFAULT 0,
                reason TEXT,
                setval_sql TEXT,
                status TEXT,
                error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(task_id) REFERENCES migration_tasks(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS data_check_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                schema_name TEXT NOT NULL,
                table_name TEXT NOT NULL,
                status TEXT NOT NULL,
                checks_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(task_id) REFERENCES migration_tasks(id)
            )
            """
        )


def ensure_columns(conn: sqlite3.Connection, table_name: str, columns: dict[str, str]) -> None:
    existing = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    for column_name, column_type in columns.items():
        if column_name not in existing:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)
