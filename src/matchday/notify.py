"""Notification channels for reminders and result alerts.

Choose channels with MATCHDAY_NOTIFY (comma-separated): console, outbox, telegram, webhook.
    outbox    appends JSON lines to MATCHDAY_OUTBOX (default .matchday/outbox.jsonl)
    telegram  needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
    webhook   POSTs {"title", "body"} as JSON to MATCHDAY_WEBHOOK_URL
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Protocol, TextIO


class Notifier(Protocol):
    name: str

    def send(self, title: str, body: str) -> None: ...


class ConsoleNotifier:
    name = "console"

    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout

    def send(self, title: str, body: str) -> None:
        print(f"[notify] {title}\n         {body}", file=self.stream)


class OutboxNotifier:
    name = "outbox"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def send(self, title: str, body: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"title": title, "body": body}) + "\n")


def _post_json(url: str, payload: dict[str, str]) -> None:
    if not url.startswith("https://"):
        raise ValueError("notification endpoints must use https")
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=15):  # noqa: S310 - https checked above
        pass


class TelegramNotifier:
    name = "telegram"

    def __init__(self, token: str, chat_id: str) -> None:
        self._token = token
        self.chat_id = chat_id

    def send(self, title: str, body: str) -> None:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        _post_json(url, {"chat_id": self.chat_id, "text": f"{title}\n\n{body}"})


class WebhookNotifier:
    name = "webhook"

    def __init__(self, url: str) -> None:
        self.url = url

    def send(self, title: str, body: str) -> None:
        _post_json(self.url, {"title": title, "body": body})


def build_notifiers(names: str | None = None, outbox: str | Path | None = None) -> list[Notifier]:
    wanted = [n.strip() for n in (names or os.environ.get("MATCHDAY_NOTIFY", "console")).split(",") if n.strip()]
    out: list[Notifier] = []
    for name in wanted:
        if name == "console":
            out.append(ConsoleNotifier())
        elif name == "outbox":
            out.append(OutboxNotifier(outbox or os.environ.get("MATCHDAY_OUTBOX", ".matchday/outbox.jsonl")))
        elif name == "telegram":
            token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
            if not (token and chat):
                raise SystemExit("telegram needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
            out.append(TelegramNotifier(token, chat))
        elif name == "webhook":
            url = os.environ.get("MATCHDAY_WEBHOOK_URL")
            if not url:
                raise SystemExit("webhook needs MATCHDAY_WEBHOOK_URL")
            out.append(WebhookNotifier(url))
        else:
            raise SystemExit(f"unknown notifier: {name}")
    return out
