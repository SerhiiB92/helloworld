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


@dataclass
class Config:
    # --- Telegram ---
    telegram_bot_token: str = field(default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.environ.get("TELEGRAM_CHAT_ID", ""))

    # --- LLM ---
    # provider: "gemini" (основной, бесплатный тариф) или "groq" (fallback).
    llm_provider: str = field(default_factory=lambda: os.environ.get("LLM_PROVIDER", "gemini").strip().lower())
    gemini_api_key: str = field(default_factory=lambda: os.environ.get("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"))
    groq_api_key: str = field(default_factory=lambda: os.environ.get("GROQ_API_KEY", ""))
    groq_model: str = field(default_factory=lambda: os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"))

    # --- Поведение дайджеста ---
    max_items: int = field(default_factory=lambda: _get_int("DIGEST_MAX_ITEMS", 7))
    lookback_hours: int = field(default_factory=lambda: _get_int("LOOKBACK_HOURS", 48))
    evergreen_count: int = field(default_factory=lambda: _get_int("EVERGREEN_COUNT", 2))
    timezone: str = field(default_factory=lambda: os.environ.get("TIMEZONE", "Europe/Warsaw"))

    # Час (0-23) по локальному времени, в который разрешена отправка.
    # Нужен, чтобы обойти проблему летнего/зимнего времени: cron в GitHub Actions
    # работает по UTC, поэтому мы запускаем воркфлоу на пару часов-кандидатов,
    # а реально шлём только когда локальный час совпадает с target_hour.
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
