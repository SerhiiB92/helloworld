"""Профили бота: нишевая настройка (что искать, как рубрицировать, откуда брать).

Один код обслуживает несколько тематических ботов (edtech, gamedev, …).
Каждый профиль — это папка profiles/<name>/ с тремя файлами:
  * profile.yaml    — тема: заголовок, критерий отбора, категории, настройки классики;
  * sources.yaml    — источники (RSS / Telegram / YouTube);
  * evergreen.json  — библиотека «вечнозелёных» инсайтов (если включена).

Профиль выбирается переменной окружения BOT_PROFILE (по умолчанию "edtech").
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROFILES_DIR = os.path.join(_HERE, "profiles")


@dataclass
class Profile:
    name: str
    dir: str
    title: str                          # заголовок дайджеста
    system_niche: str                   # описание ниши для системного промпта
    summary_hint: str                   # что должно доносить саммари
    criteria: str                       # критерий релевантности (текст для LLM)
    categories: list[tuple[str, str]]   # (название, эмодзи) в порядке вывода

    # Классика (evergreen)
    evergreen_enabled: bool = False
    evergreen_header: str = ""
    example_label: str = "Приклад"
    illustrate_system: str = ""         # промпт генерации живых примеров
    niches: list[str] = field(default_factory=list)  # конкретные ниши для примеров

    @property
    def sources_path(self) -> str:
        return os.path.join(self.dir, "sources.yaml")

    @property
    def evergreen_path(self) -> str:
        return os.path.join(self.dir, "evergreen.json")

    @property
    def state_path(self) -> str:
        return os.path.join(self.dir, "state.json")

    @property
    def default_category(self) -> str:
        return self.categories[0][0] if self.categories else "Новини"

    def category_names(self) -> list[str]:
        return [name for name, _ in self.categories]


def load_profile(name: str) -> Profile:
    name = (name or "edtech").strip()
    pdir = os.path.join(_PROFILES_DIR, name)
    ppath = os.path.join(pdir, "profile.yaml")
    if not os.path.isfile(ppath):
        raise FileNotFoundError(f"Профиль '{name}' не найден: нет {ppath}")

    with open(ppath, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    categories = [
        (c["name"], c.get("emoji", "📰"))
        for c in data.get("categories", [])
        if c.get("name")
    ]

    eg = data.get("evergreen", {}) or {}

    return Profile(
        name=name,
        dir=pdir,
        title=data.get("title", "Digest"),
        system_niche=data.get("system_niche", ""),
        summary_hint=data.get("summary_hint", ""),
        criteria=data.get("criteria", "").strip(),
        categories=categories,
        evergreen_enabled=bool(eg.get("enabled", False)),
        evergreen_header=eg.get("header", ""),
        example_label=eg.get("example_label", "Приклад"),
        illustrate_system=(eg.get("illustrate_system", "") or "").strip(),
        niches=list(eg.get("niches", [])),
    )
