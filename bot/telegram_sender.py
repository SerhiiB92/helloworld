"""Отправка сообщений в Telegram через Bot API (напрямую по HTTP)."""

from __future__ import annotations

import logging
import time

import httpx

log = logging.getLogger("telegram")

_TELEGRAM_LIMIT = 4096  # максимум символов в одном сообщении


def _split_message(text: str, limit: int = _TELEGRAM_LIMIT) -> list[str]:
    """Режем длинный дайджест на части по границам абзацев (пустая строка)."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for block in text.split("\n\n"):
        candidate = block if not current else current + "\n\n" + block
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # сам блок может быть длиннее лимита — режем жёстко
            while len(block) > limit:
                chunks.append(block[:limit])
                block = block[limit:]
            current = block
    if current:
        chunks.append(current)
    return chunks


def send_message(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    for chunk in _split_message(text):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
        _post_with_retry(url, payload)
        time.sleep(0.5)  # мягко, чтобы не упереться в rate limit


def _post_with_retry(url: str, payload: dict, attempts: int = 4) -> None:
    delay = 2.0
    for attempt in range(1, attempts + 1):
        try:
            resp = httpx.post(url, json=payload, timeout=30.0)
            if resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", delay)
                log.warning("Telegram rate limit, жду %s c", retry_after)
                time.sleep(float(retry_after))
                continue
            resp.raise_for_status()
            return
        except httpx.HTTPError as exc:
            log.warning("Ошибка отправки в Telegram (попытка %d/%d): %s", attempt, attempts, exc)
            if attempt == attempts:
                raise
            time.sleep(delay)
            delay *= 2
