"""Конфигурация бота.

Все настройки берутся из переменных окружения (в GitHub Actions — из Secrets),
чтобы ключи никогда не попадали в репозиторий. Значения по умолчанию подобраны
так, чтобы бот заработал сразу после подстановки двух ключей:
TELEGRAM_BOT_TOKEN и GEMINI_API_KEY.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _get_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    if val is None or not val.strip():
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _get_str(name: str, default: str = "") -> str:
    """Читает переменную и ОБРЕЗАЕТ пробелы/переносы строки.

    Частая беда: ключ или токен вставляют в GitHub Secrets с лишним \\n на
    конце. Тогда, например, Gemini отвечает 401. strip() делает это неважным.
    """
    return os.environ.get(name, default).strip()


@dataclass
class Config:
    # Профиль бота (папка profiles/<name>/): "edtech", "gamedev", …
    bot_profile: str = field(default_factory=lambda: _get_str("BOT_PROFILE", "edtech"))

    # --- Telegram ---
    # Все ключи/токены читаем через _get_str — он обрезает пробелы и переносы
    # строк (иначе лишний \n в секрете ломает запросы, напр. Gemini → 401).
    telegram_bot_token: str = field(default_factory=lambda: _get_str("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = field(default_factory=lambda: _get_str("TELEGRAM_CHAT_ID"))

    # --- LLM ---
    # provider: "gemini" (основной, бесплатный тариф) или "groq" (fallback).
    llm_provider: str = field(default_factory=lambda: _get_str("LLM_PROVIDER", "gemini").lower())
    gemini_api_key: str = field(default_factory=lambda: _get_str("GEMINI_API_KEY"))
    gemini_model: str = field(default_factory=lambda: _get_str("GEMINI_MODEL", "gemini-2.0-flash"))
    # Запасные модели Gemini (тот же ключ). Если основная упирается в 429/лимит,
    # бот по очереди пробует эти. gemini-1.5-flash убран — Google его отключил (404).
    gemini_fallback_models: list[str] = field(
        default_factory=lambda: [
            m.strip()
            for m in _get_str("GEMINI_FALLBACK_MODELS", "gemini-2.5-flash,gemini-2.0-flash-lite").split(",")
            if m.strip()
        ]
    )
    groq_api_key: str = field(default_factory=lambda: _get_str("GROQ_API_KEY"))
    groq_model: str = field(default_factory=lambda: _get_str("GROQ_MODEL", "llama-3.3-70b-versatile"))

    # --- Поведение дайджеста ---
    max_items: int = field(default_factory=lambda: _get_int("DIGEST_MAX_ITEMS", 7))
    # Максимум кандидатов, которых отдаём в LLM за один запрос (источников много —
    # берём самые свежие). Держим компактным: у Groq есть лимит на размер запроса
    # (иначе 413 Payload Too Large). 30 свежих с коротким текстом влезают надёжно.
    max_candidates: int = field(default_factory=lambda: _get_int("MAX_CANDIDATES", 30))
    lookback_hours: int = field(default_factory=lambda: _get_int("LOOKBACK_HOURS", 48))
    evergreen_count: int = field(default_factory=lambda: _get_int("EVERGREEN_COUNT", 2))
    timezone: str = field(default_factory=lambda: os.environ.get("TIMEZONE", "Europe/Warsaw"))

    # Целевой локальный час (0-23). Дайджест уходит ОДИН раз в день, при первом
    # запуске в или после этого часа (см. main.py + state.last_sent_date). Так
    # обходятся и перевод часов, и задержки/пропуски GitHub-крона.
    # Пусто = проверки нет (шлём при любом запуске) — удобно для ручного теста.
    target_hour: int | None = field(
        default_factory=lambda: _get_int("TARGET_HOUR", -1) if os.environ.get("TARGET_HOUR", "").strip() else None
    )

    # dry-run: не отправлять в Telegram, а печатать в консоль (для локальной отладки).
    dry_run: bool = field(default_factory=lambda: _get_bool("DRY_RUN", False))

    def validate_for_send(self) -> list[str]:
        """Возвращает список проблем, из-за которых нельзя отправить дайджест."""
        problems: list[str] = []
        if not self.dry_run:
            if not self.telegram_bot_token:
                problems.append("Не задан TELEGRAM_BOT_TOKEN")
            if not self.telegram_chat_id:
                problems.append("Не задан TELEGRAM_CHAT_ID")
        if self.llm_provider == "gemini" and not self.gemini_api_key:
            problems.append("LLM_PROVIDER=gemini, но не задан GEMINI_API_KEY")
        if self.llm_provider == "groq" and not self.groq_api_key:
            problems.append("LLM_PROVIDER=groq, но не задан GROQ_API_KEY")
        return problems


def load_config() -> Config:
    return Config()
