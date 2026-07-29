"""Общие структуры данных."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Item:
    """Одна собранная запись из источника (статья, пост, видео)."""

    title: str
    url: str
    source: str                       # человекочитаемое имя источника
    source_type: str                  # "rss" | "telegram" | "youtube"
    summary: str = ""                 # исходный текст/описание (сырой, до LLM)
    published: Optional[datetime] = None

    @property
    def uid(self) -> str:
        """Стабильный идентификатор для антидублей (по URL)."""
        return hashlib.sha256(self.url.strip().encode("utf-8")).hexdigest()[:16]

    def to_candidate(self) -> dict:
        """Компактное представление для передачи в LLM."""
        text = self.summary.strip().replace("\n", " ")
        # Короткий сниппет: для оценки релевантности хватает, а запрос к LLM
        # остаётся компактным (у Groq лимит на размер тела запроса — иначе 413).
        if len(text) > 150:
            text = text[:150] + "…"
        title = self.title.strip()
        if len(title) > 160:
            title = title[:160] + "…"
        return {
            "id": self.uid,
            "title": title,
            "source": self.source,
            "type": self.source_type,
            "text": text,
            "url": self.url,
        }


@dataclass
class DigestEntry:
    """Відібраний і оброблений LLM запис, готовий до верстки (українською)."""

    title: str
    summary: str
    category: str
    url: str
    source: str
