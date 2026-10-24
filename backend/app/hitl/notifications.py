"""Notify reviewers when items are waiting (Slack-compatible webhook, or just a log line)."""
from __future__ import annotations

import threading

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)


class Notifier:
    def __init__(self, webhook_url: str | None = None, timeout: float = 5.0):
        self.webhook_url = webhook_url
        self.timeout = timeout

    def notify(self, message: str) -> None:
        """Fire-and-forget; never blocks or fails the request."""
        logger.info("[HITL] %s", message)
        if not self.webhook_url:
            return
        threading.Thread(target=self._post, args=(message,), daemon=True).start()

    def _post(self, message: str) -> None:
        try:
            httpx.post(self.webhook_url, json={"text": message}, timeout=self.timeout)
        except httpx.HTTPError as exc:
            logger.warning("Reviewer notification failed: %s", exc)
