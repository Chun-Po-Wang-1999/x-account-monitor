from __future__ import annotations

import json
import tempfile
from pathlib import Path

import google.auth
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload


SCOPES = ["https://www.googleapis.com/auth/drive"]


class DriveSync:
    def __init__(
        self,
        *,
        folder_id: str,
        service_account_json: str | None,
        application_credentials: str | None,
    ) -> None:
        credentials = self._credentials(service_account_json, application_credentials)
        self.service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        self.folder_id = folder_id

    def _credentials(self, inline_json: str | None, path: str | None):
        if inline_json:
            info = json.loads(inline_json)
            return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        if path:
            return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
        credentials, _ = google.auth.default(scopes=SCOPES)
        return credentials

    def _find_file(
        self,
        name: str,
        *,
        parent_id: str | None = None,
        mime_type: str | None = None,
    ) -> str | None:
        parent_id = parent_id or self.folder_id
        escaped_name = name.replace("'", "\\'")
        query = (
            f"name = '{escaped_name}' and '{parent_id}' in parents "
            "and trashed = false"
        )
        if mime_type:
            query += f" and mimeType = '{mime_type}'"
        response = (
            self.service.files()
            .list(q=query, spaces="drive", fields="files(id, name)", pageSize=1)
            .execute()
        )
        files = response.get("files", [])
        return files[0]["id"] if files else None

    def download_if_exists(self, *, name: str, destination: Path) -> bool:
        file_id = self._find_file(name)
        if not file_id:
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        request = self.service.files().get_media(fileId=file_id)
        with destination.open("wb") as handle:
            downloader = MediaIoBaseDownload(handle, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        return True

    def ensure_folder(self, name: str, *, parent_id: str | None = None) -> str:
        folder_mime = "application/vnd.google-apps.folder"
        file_id = self._find_file(name, parent_id=parent_id, mime_type=folder_mime)
        if file_id:
            return file_id
        metadata = {
            "name": name,
            "parents": [parent_id or self.folder_id],
            "mimeType": folder_mime,
        }
        response = self.service.files().create(body=metadata, fields="id").execute()
        return response["id"]

    def upload_file(
        self,
        *,
        source: Path,
        name: str,
        mime_type: str = "application/octet-stream",
        parent_id: str | None = None,
    ) -> None:
        parent_id = parent_id or self.folder_id
        file_id = self._find_file(name, parent_id=parent_id)
        media = MediaFileUpload(str(source), mimetype=mime_type, resumable=False)
        if file_id:
            self.service.files().update(fileId=file_id, media_body=media).execute()
            return
        metadata = {"name": name, "parents": [parent_id]}
        self.service.files().create(body=metadata, media_body=media, fields="id").execute()

    def create_lock(self, *, name: str, contents: str) -> bool:
        if self._find_file(name):
            return False
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write(contents)
            temp_path = Path(handle.name)
        try:
            self.upload_file(source=temp_path, name=name, mime_type="text/plain")
            return True
        finally:
            temp_path.unlink(missing_ok=True)

    def delete_file(self, *, name: str) -> None:
        file_id = self._find_file(name)
        if file_id:
            self.service.files().delete(fileId=file_id).execute()


def text_mime(path: Path) -> str:
    if path.suffix.lower() == ".md":
        return "text/markdown"
    if path.suffix.lower() == ".txt":
        return "text/plain"
    return "application/octet-stream"
