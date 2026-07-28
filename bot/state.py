"""Хранилище состояния между запусками.

Держим в одном JSON-файле (по умолчанию state.json), который GitHub Actions
коммитит обратно в репозиторий после каждого запуска. Для одного пользователя
этого достаточно — без БД и внешних сервисов.

Структура:
{
  "seen_news":      ["<uid>", ...],   # уже присланные новости (по URL-хешу)
  "seen_evergreen": ["<id>", ...]     # уже показанные вечнозелёные инсайты
}
"""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("state")

# Ограничиваем историю новостей, чтобы файл не рос бесконечно.
_MAX_SEEN_NEWS = 4000


class State:
    def __init__(self, path: str):
        self.path = path
        self.seen_news: list[str] = []
        self.seen_evergreen: list[str] = []
        # Дата последней отправки (ISO, локальная) — чтобы слать максимум раз в день.
        self.last_sent_date: str = ""
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            log.info("Файл состояния не найден, начинаю с чистого листа: %s", self.path)
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.seen_news = list(data.get("seen_news", []))
            self.seen_evergreen = list(data.get("seen_evergreen", []))
            self.last_sent_date = str(data.get("last_sent_date", ""))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Не удалось прочитать состояние (%s), начинаю заново", exc)

    def is_news_seen(self, uid: str) -> bool:
        return uid in self._seen_news_set

    @property
    def _seen_news_set(self) -> set[str]:
        # кэшируем множество на время жизни объекта
        if not hasattr(self, "_news_set_cache"):
            self._news_set_cache = set(self.seen_news)
        return self._news_set_cache

    def mark_news(self, uids: list[str]) -> None:
        for uid in uids:
            if uid not in self._seen_news_set:
                self.seen_news.append(uid)
                self._seen_news_set.add(uid)
        # обрезаем самые старые
        if len(self.seen_news) > _MAX_SEEN_NEWS:
            self.seen_news = self.seen_news[-_MAX_SEEN_NEWS:]
            self._news_set_cache = set(self.seen_news)

    def mark_evergreen(self, ids: list[str], total_available: int) -> None:
        for eid in ids:
            if eid not in self.seen_evergreen:
                self.seen_evergreen.append(eid)
        # когда показали все инсайты — начинаем цикл заново
        if len(self.seen_evergreen) >= total_available:
            log.info("Все вечнозелёные инсайты показаны — сбрасываю цикл")
            self.seen_evergreen = list(ids)

    def save(self) -> None:
        data = {
            "seen_news": self.seen_news,
            "seen_evergreen": self.seen_evergreen,
            "last_sent_date": self.last_sent_date,
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        log.info("Состояние сохранено: %s", self.path)
