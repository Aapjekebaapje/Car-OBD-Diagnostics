import json
import sqlite3
from pathlib import Path


def db_path_from_file(app_file):
    return Path(app_file).with_name("scanner_config.db")


def init_storage(db_path):
    with sqlite3.connect(db_path) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                label TEXT NOT NULL,
                summary TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        db.commit()


def get_setting(db_path, key, default=None):
    with sqlite3.connect(db_path) as db:
        row = db.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ).fetchone()

    return row[0] if row else default


def set_setting(db_path, key, value):
    with sqlite3.connect(db_path) as db:
        db.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        db.commit()

    return True


def save_scan_snapshot(db_path, created_at, label, summary, payload):
    with sqlite3.connect(db_path) as db:
        db.execute(
            """
            INSERT INTO scans (created_at, label, summary, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (created_at, label, summary, json.dumps(payload)),
        )
        db.commit()

    return {
        "created_at": created_at,
        "label": label,
        "summary": summary,
    }


def get_recent_scans(db_path, limit):
    with sqlite3.connect(db_path) as db:
        rows = db.execute(
            """
            SELECT id, created_at, label, summary, payload_json
            FROM scans
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    scans = []
    for row in rows:
        scans.append(
            {
                "id": row[0],
                "created_at": row[1],
                "label": row[2],
                "summary": row[3],
                "payload": json.loads(row[4]),
            }
        )

    return scans
