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
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS garage_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                vin TEXT NOT NULL DEFAULT '',
                plate TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                mileage TEXT NOT NULL,
                note TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        existing_columns = {
            row[1]
            for row in db.execute("PRAGMA table_info(garage_notes)").fetchall()
        }
        if "vin" not in existing_columns:
            db.execute("ALTER TABLE garage_notes ADD COLUMN vin TEXT NOT NULL DEFAULT ''")
        if "plate" not in existing_columns:
            db.execute("ALTER TABLE garage_notes ADD COLUMN plate TEXT NOT NULL DEFAULT ''")
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


def save_garage_note(db_path, created_at, vin, plate, title, mileage, note, payload):
    with sqlite3.connect(db_path) as db:
        db.execute(
            """
            INSERT INTO garage_notes (created_at, vin, plate, title, mileage, note, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (created_at, vin, plate, title, mileage, note, json.dumps(payload)),
        )
        db.commit()

    return {
        "created_at": created_at,
        "vin": vin,
        "plate": plate,
        "title": title,
        "mileage": mileage,
        "note": note,
    }


def get_recent_garage_notes(db_path, limit):
    with sqlite3.connect(db_path) as db:
        rows = db.execute(
            """
            SELECT id, created_at, vin, plate, title, mileage, note, payload_json
            FROM garage_notes
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    notes = []
    for row in rows:
        notes.append(
            {
                "id": row[0],
                "created_at": row[1],
                "vin": row[2],
                "plate": row[3],
                "title": row[4],
                "mileage": row[5],
                "note": row[6],
                "payload": json.loads(row[7]),
            }
        )

    return notes
