from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


BASE_URL = "https://api.x.com/2"


@dataclass(frozen=True)
class XUser:
    id: str
    username: str
    name: str | None
    raw: dict[str, Any]


class XApiClient:
    def __init__(self, bearer_token: str) -> None:
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {bearer_token}"})

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.get(f"{BASE_URL}{path}", params=params, timeout=30)
        if response.status_code >= 400:
            raise RuntimeError(
                f"X API request failed: {response.status_code} {response.text[:500]}"
            )
        return response.json()

    def get_user_by_username(self, username: str) -> XUser:
        payload = self._get(
            f"/users/by/username/{username}",
            params={"user.fields": "id,name,username,created_at,description,verified"},
        )
        data = payload["data"]
        return XUser(
            id=data["id"],
            username=data["username"],
            name=data.get("name"),
            raw=payload,
        )

    def get_user_posts(
        self,
        user_id: str,
        *,
        since_id: str | None,
        exclude_retweets: bool,
        max_pages: int,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "max_results": 100,
            "tweet.fields": ",".join(
                [
                    "attachments",
                    "author_id",
                    "conversation_id",
                    "created_at",
                    "entities",
                    "in_reply_to_user_id",
                    "lang",
                    "public_metrics",
                    "referenced_tweets",
                    "reply_settings",
                    "possibly_sensitive",
                ]
            ),
            "expansions": "attachments.media_keys,referenced_tweets.id",
            "media.fields": "media_key,type,url,preview_image_url,alt_text",
        }
        if since_id:
            params["since_id"] = since_id
        if exclude_retweets:
            params["exclude"] = "retweets"

        posts: list[dict[str, Any]] = []
        next_token: str | None = None
        for _ in range(max_pages):
            page_params = dict(params)
            if next_token:
                page_params["pagination_token"] = next_token
            payload = self._get(f"/users/{user_id}/tweets", params=page_params)
            includes = payload.get("includes", {})
            for item in payload.get("data", []):
                item["_includes"] = includes
                posts.append(item)
            next_token = payload.get("meta", {}).get("next_token")
            if not next_token:
                break
        return posts


def classify_post(post: dict[str, Any]) -> str:
    referenced = post.get("referenced_tweets") or []
    types = {item.get("type") for item in referenced}
    if "retweeted" in types:
        return "repost"
    if "replied_to" in types:
        return "reply"
    if "quoted" in types:
        return "quote"
    return "original"


def post_url(username: str, post_id: str) -> str:
    return f"https://x.com/{username}/status/{post_id}"
