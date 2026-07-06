from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            PRAGMA journal_mode=DELETE;

            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                display_name TEXT,
                raw_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS posts (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                post_type TEXT NOT NULL,
                conversation_id TEXT,
                in_reply_to_user_id TEXT,
                referenced_post_ids TEXT NOT NULL,
                url TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                inserted_at TEXT NOT NULL,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            );

            CREATE INDEX IF NOT EXISTS idx_posts_account_created
                ON posts(account_id, created_at);

            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                new_post_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT
            );
            """
        )
        self.conn.commit()

    def start_run(self) -> int:
        cursor = self.conn.execute(
            "INSERT INTO runs (started_at, status) VALUES (?, ?)",
            (utc_now_iso(), "running"),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        new_post_count: int,
        error_message: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE runs
            SET finished_at = ?, status = ?, new_post_count = ?,
                error_message = ?
            WHERE id = ?
            """,
            (utc_now_iso(), status, new_post_count, error_message, run_id),
        )
        self.conn.commit()

    def upsert_account(self, account_id: str, username: str, display_name: str | None, raw: Any) -> None:
        self.conn.execute(
            """
            INSERT INTO accounts (id, username, display_name, raw_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username = excluded.username,
                display_name = excluded.display_name,
                raw_json = excluded.raw_json,
                updated_at = excluded.updated_at
            """,
            (account_id, username, display_name, json.dumps(raw), utc_now_iso()),
        )
        self.conn.commit()

    def latest_post_id(self, account_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT id FROM posts WHERE account_id = ? ORDER BY CAST(id AS INTEGER) DESC LIMIT 1",
            (account_id,),
        ).fetchone()
        return str(row["id"]) if row else None

    def insert_posts(self, posts: Iterable[dict[str, Any]]) -> list[str]:
        inserted: list[str] = []
        for post in posts:
            cursor = self.conn.execute(
                """
                INSERT OR IGNORE INTO posts (
                    id, account_id, username, created_at, text, post_type,
                    conversation_id, in_reply_to_user_id, referenced_post_ids,
                    url, raw_json, inserted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    post["id"],
                    post["account_id"],
                    post["username"],
                    post["created_at"],
                    post["text"],
                    post["post_type"],
                    post.get("conversation_id"),
                    post.get("in_reply_to_user_id"),
                    json.dumps(post.get("referenced_post_ids", [])),
                    post["url"],
                    json.dumps(post["raw_json"]),
                    utc_now_iso(),
                ),
            )
            if cursor.rowcount:
                inserted.append(post["id"])
        self.conn.commit()
        return inserted

    def get_posts_by_ids(self, post_ids: list[str]) -> list[sqlite3.Row]:
        if not post_ids:
            return []
        placeholders = ",".join("?" for _ in post_ids)
        return list(
            self.conn.execute(
                f"SELECT * FROM posts WHERE id IN ({placeholders}) ORDER BY created_at ASC",
                post_ids,
            )
        )
