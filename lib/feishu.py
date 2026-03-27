"""Feishu messaging client with group routing and dedup.

Six groups as permission-isolated interaction interfaces:
- Tailmon (data purifier): ingestion only
- Agumon (web tracker): fetch and return only
- Gabumon (rule arbiter): approval layer, human sovereignty
- Gomamon (logic inquisitor): broadcasts, reviews, challenges
- Kabuterimon (code tinkerer): system faults, L1 alerts
- Patamon (vault keeper): private retrieval, human-wake only
"""

import hashlib
import sqlite3
from datetime import datetime, timezone

import requests

FEISHU_GROUPS = {
    "tailmon": "oc_7bd7e7096c9a3be8e686ac70f6dcac5b",
    "agumon": "oc_185c03a6d083dc9dd99d3ed24361e171",
    "gabumon": "oc_cd1a764eb1ac0b024462119e0d402210",
    "gomamon": "oc_e3bf797d93e4a3365fc0cdd9b99b429b",
    "kabuterimon": "oc_5c9ae741c8b54919b3d87b832493d6b5",
    "patamon": "oc_62e97e4c8e6a6e90738ce6e76a4dbd62",
}

DEDUPE_WINDOW_SECONDS = 300


class FeishuClient:
    """Feishu messaging with group routing and content dedup."""

    def __init__(self, app_id: str, app_secret: str, conn: sqlite3.Connection):
        self._app_id = app_id
        self._app_secret = app_secret
        self._conn = conn
        self._token: str | None = None

    def _get_token(self) -> str:
        """Get or refresh tenant access token."""
        if self._token:
            return self._token
        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self._app_id, "app_secret": self._app_secret},
        )
        self._token = resp.json().get("tenant_access_token", "")
        return self._token

    def _content_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()

    def _is_deduped(self, content_hash: str, group_id: str) -> bool:
        """Check if this content was recently sent to this group."""
        row = self._conn.execute(
            "SELECT sent_at FROM feishu_dedupe WHERE content_hash=? AND group_id=?",
            (content_hash, group_id),
        ).fetchone()
        if row is None:
            return False
        sent_at = datetime.fromisoformat(row["sent_at"])
        now = datetime.now(timezone.utc)
        return (now - sent_at).total_seconds() < DEDUPE_WINDOW_SECONDS

    def _record_send(self, content_hash: str, group_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO feishu_dedupe (content_hash, group_id, sent_at) "
            "VALUES (?, ?, ?)",
            (content_hash, group_id, now),
        )
        self._conn.commit()

    def send_to_group(self, group_name: str, content: str) -> dict:
        """Send a text message to a named Feishu group.

        Returns dict with 'sent' bool and optional 'reason'.
        """
        if group_name not in FEISHU_GROUPS:
            raise ValueError(f"Unknown group: {group_name!r}")

        group_id = FEISHU_GROUPS[group_name]
        content_hash = self._content_hash(content)

        if self._is_deduped(content_hash, group_id):
            return {"sent": False, "reason": "dedup", "group": group_name}

        try:
            token = self._get_token()
            resp = requests.post(
                "https://open.feishu.cn/open-apis/im/v1/messages",
                headers={"Authorization": f"Bearer {token}"},
                params={"receive_id_type": "chat_id"},
                json={
                    "receive_id": group_id,
                    "msg_type": "text",
                    "content": f'{{"text": "{content}"}}',
                },
                timeout=10,
            )
            self._record_send(content_hash, group_id)
            return {"sent": True, "group": group_name, "status_code": resp.status_code}
        except Exception as e:
            return {"sent": False, "reason": str(e), "group": group_name}

    @staticmethod
    def route_alert(level: str) -> str:
        """Determine which group receives an alert based on level."""
        if level == "L1":
            return "kabuterimon"
        return "gomamon"

    @staticmethod
    def route_approval() -> str:
        """Approval requests always go to Gabumon."""
        return "gabumon"
