from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    target_username: str
    x_bearer_token: str
    work_dir: Path
    sqlite_filename: str
    google_drive_folder_id: str | None
    google_service_account_json: str | None
    google_application_credentials: str | None
    exclude_retweets: bool
    max_pages: int

    @property
    def db_path(self) -> Path:
        return self.work_dir / self.sqlite_filename

def load_settings() -> Settings:
    return Settings(
        target_username=os.getenv("TARGET_USERNAME", "aleabitoreddit").lstrip("@"),
        x_bearer_token=os.getenv("X_BEARER_TOKEN", ""),
        work_dir=Path(os.getenv("WORK_DIR", "/tmp/x_account_monitor")),
        sqlite_filename=os.getenv("SQLITE_FILENAME", "aleabitoreddit.sqlite"),
        google_drive_folder_id=os.getenv("GOOGLE_DRIVE_FOLDER_ID") or None,
        google_service_account_json=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or None,
        google_application_credentials=os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or None,
        exclude_retweets=_bool_env("EXCLUDE_RETWEETS", True),
        max_pages=max(1, int(os.getenv("MAX_PAGES", "20"))),
    )


def validate_settings(settings: Settings) -> None:
    missing = []
    if not settings.x_bearer_token:
        missing.append("X_BEARER_TOKEN")
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
