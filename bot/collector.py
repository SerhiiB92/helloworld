"""Сбор записей из всех источников: RSS, публичные Telegram-каналы, YouTube.

Принцип: максимальная устойчивость. Любой отдельный источник может быть
недоступен/сломан — мы логируем и идём дальше, но не падаем целиком.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable

import feedparser
import httpx
import yaml
from dateutil import parser as date_parser
from selectolax.parser import HTMLParser

from models import Item

log = logging.getLogger("collector")

_HTTP_TIMEOUT = 20.0
_USER_AGENT = (
    "Mozilla/5.0 (compatible; EdTechDigestBot/1.0; +https://github.com/)"
)


def load_sources(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("rss", [])
    data.setdefault("telegram", [])
    data.setdefault("youtube", [])
    return data


def _parse_date(entry) -> datetime | None:
    """Пытается вытащить дату публикации из записи фида (в UTC)."""
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
    for key in ("published", "updated"):
        raw = entry.get(key)
        if raw:
            try:
                dt = date_parser.parse(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except (ValueError, OverflowError):
                pass
    return None


def _clean_html(raw: str) -> str:
    if not raw:
        return ""
    try:
        return HTMLParser(raw).text(separator=" ", strip=True)
    except Exception:  # noqa: BLE001 - парсер не должен ронять сбор
        return raw


def _fetch_feed(url: str) -> feedparser.FeedParserDict | None:
    """Скачиваем фид через httpx (со своим User-Agent) и парсим feedparser'ом."""
    try:
        resp = httpx.get(
            url,
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("Не удалось скачать фид %s: %s", url, exc)
        return None
    return feedparser.parse(resp.content)


def collect_rss(feeds: list[dict], cutoff: datetime) -> list[Item]:
    items: list[Item] = []
    for feed in feeds:
        name = feed.get("name") or feed.get("url", "RSS")
        url = feed.get("url")
        if not url:
            continue
        parsed = _fetch_feed(url)
        if parsed is None:
            continue
        for entry in parsed.entries:
            published = _parse_date(entry)
            if published and published < cutoff:
                continue
            link = entry.get("link")
            title = entry.get("title")
            if not link or not title:
                continue
            summary = _clean_html(entry.get("summary", "") or entry.get("description", ""))
            items.append(
                Item(
                    title=title,
                    url=link,
                    source=name,
                    source_type="rss",
                    summary=summary,
                    published=published,
                )
            )
    log.info("RSS: собрано %d записей", len(items))
    return items


def collect_youtube(channels: list[dict], cutoff: datetime) -> list[Item]:
    """YouTube отдаёт RSS по адресу feeds/videos.xml?channel_id=UC..."""
    items: list[Item] = []
    for ch in channels:
        channel_id = ch.get("channel_id")
        name = ch.get("name") or channel_id
        if not channel_id:
            continue
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        parsed = _fetch_feed(url)
        if parsed is None:
            continue
        for entry in parsed.entries:
            published = _parse_date(entry)
            if published and published < cutoff:
                continue
            link = entry.get("link")
            title = entry.get("title")
            if not link or not title:
                continue
            media = entry.get("media_description", "") or entry.get("summary", "")
            items.append(
                Item(
                    title=title,
                    url=link,
                    source=f"YouTube · {name}",
                    source_type="youtube",
                    summary=_clean_html(media),
                    published=published,
                )
            )
    log.info("YouTube: собрано %d записей", len(items))
    return items


def collect_telegram(usernames: list[str], cutoff: datetime) -> list[Item]:
    """Читаем публичные каналы через веб-превью https://t.me/s/<username>.

    Это официальная публичная веб-версия канала — не требует ни userbot,
    ни вашего аккаунта. Работает только для публичных каналов.
    """
    items: list[Item] = []
    for username in usernames:
        username = str(username).lstrip("@").strip()
        if not username:
            continue
        url = f"https://t.me/s/{username}"
        try:
            resp = httpx.get(
                url,
                timeout=_HTTP_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("Не удалось прочитать TG-канал @%s: %s", username, exc)
            continue

        tree = HTMLParser(resp.text)
        for node in tree.css("div.tgme_widget_message_wrap"):
            msg = node.css_first("div.tgme_widget_message")
            if msg is None:
                continue

            # Ссылка на конкретный пост
            link_node = node.css_first("a.tgme_widget_message_date")
            post_url = link_node.attributes.get("href") if link_node else None
            if not post_url:
                data_post = msg.attributes.get("data-post")
                post_url = f"https://t.me/{data_post}" if data_post else url

            # Дата
            published = None
            time_node = node.css_first("time")
            if time_node and time_node.attributes.get("datetime"):
                try:
                    published = date_parser.parse(time_node.attributes["datetime"])
                    if published.tzinfo is None:
                        published = published.replace(tzinfo=timezone.utc)
                    published = published.astimezone(timezone.utc)
                except (ValueError, OverflowError):
                    published = None
            if published and published < cutoff:
                continue

            text_node = node.css_first("div.tgme_widget_message_text")
            text = text_node.text(separator=" ", strip=True) if text_node else ""
            if not text:
                continue

            # Заголовок = первая строка/первые слова поста
            title = text.strip().split("\n")[0][:200]
            items.append(
                Item(
                    title=title,
                    url=post_url,
                    source=f"TG · @{username}",
                    source_type="telegram",
                    summary=text,
                    published=published,
                )
            )
    log.info("Telegram: собрано %d записей", len(items))
    return items


def collect_all(sources: dict, lookback_hours: int) -> list[Item]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    items: list[Item] = []
    items += collect_rss(sources.get("rss", []), cutoff)
    items += collect_youtube(sources.get("youtube", []), cutoff)
    items += collect_telegram(sources.get("telegram", []), cutoff)
    return _dedupe(items)


def _dedupe(items: Iterable[Item]) -> list[Item]:
    """Убираем повторы по URL, сохраняя порядок."""
    seen: set[str] = set()
    out: list[Item] = []
    for item in items:
        if item.uid in seen:
            continue
        seen.add(item.uid)
        out.append(item)
    return out
