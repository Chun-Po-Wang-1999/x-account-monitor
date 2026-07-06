from __future__ import annotations

import json
import sys
from typing import Any

from .config import load_settings, validate_settings
from .drive_sync import DriveSync
from .storage import Store, utc_now_iso
from .x_client import XApiClient, classify_post, post_url


LOCK_NAME = "x_account_monitor.lock"


def normalize_post(raw: dict[str, Any], *, account_id: str, username: str) -> dict[str, Any]:
    referenced = raw.get("referenced_tweets") or []
    return {
        "id": raw["id"],
        "account_id": account_id,
        "username": username,
        "created_at": raw["created_at"],
        "text": raw.get("text", ""),
        "post_type": classify_post(raw),
        "conversation_id": raw.get("conversation_id"),
        "in_reply_to_user_id": raw.get("in_reply_to_user_id"),
        "referenced_post_ids": [item["id"] for item in referenced if "id" in item],
        "url": post_url(username, raw["id"]),
        "raw_json": raw,
    }


def build_drive(settings) -> DriveSync | None:
    if not settings.google_drive_folder_id:
        return None
    return DriveSync(
        folder_id=settings.google_drive_folder_id,
        service_account_json=settings.google_service_account_json,
        application_credentials=settings.google_application_credentials,
    )


def main() -> int:
    settings = load_settings()
    validate_settings(settings)
    settings.work_dir.mkdir(parents=True, exist_ok=True)

    drive = build_drive(settings)
    lock_acquired = False
    if drive:
        lock_acquired = drive.create_lock(
            name=LOCK_NAME,
            contents=json.dumps({"created_at": utc_now_iso(), "username": settings.target_username}),
        )
        if not lock_acquired:
            print("Another run appears to be active because the Drive lock file exists.")
            return 2
        downloaded = drive.download_if_exists(
            name=settings.sqlite_filename,
            destination=settings.db_path,
        )
        print(f"Drive database download: {'found existing database' if downloaded else 'starting fresh'}")

    store = Store(settings.db_path)
    run_id: int | None = None
    new_post_ids: list[str] = []
    try:
        store.init_schema()
        run_id = store.start_run()

        x_client = XApiClient(settings.x_bearer_token)
        user = x_client.get_user_by_username(settings.target_username)
        store.upsert_account(user.id, user.username, user.name, user.raw)

        since_id = store.latest_post_id(user.id)
        raw_posts = x_client.get_user_posts(
            user.id,
            since_id=since_id,
            exclude_retweets=settings.exclude_retweets,
            max_pages=settings.max_pages,
        )
        normalized = [
            normalize_post(raw, account_id=user.id, username=user.username)
            for raw in raw_posts
        ]
        normalized.sort(key=lambda item: int(item["id"]))
        new_post_ids = store.insert_posts(normalized)

        store.finish_run(
            run_id,
            status="success",
            new_post_count=len(new_post_ids),
        )
        print(f"Run completed. New posts: {len(new_post_ids)}.")
    except Exception as exc:
        if run_id is not None:
            store.finish_run(
                run_id,
                status="failed",
                new_post_count=len(new_post_ids),
                error_message=str(exc),
            )
        print(f"Run failed: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()
        if drive:
            try:
                if settings.db_path.exists():
                    drive.upload_file(source=settings.db_path, name=settings.sqlite_filename)
            finally:
                if lock_acquired:
                    drive.delete_file(name=LOCK_NAME)
    return 0
