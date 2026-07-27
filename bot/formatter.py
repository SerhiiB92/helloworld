"""Вёрстка дайджеста в HTML для Telegram.

Telegram поддерживает ограниченный HTML (parse_mode=HTML). Используем его,
потому что он надёжнее Markdown в плане экранирования спецсимволов.
"""

from __future__ import annotations

from datetime import datetime
from html import escape

from models import DigestEntry

# Порядок та емодзі категорій новин.
_CATEGORY_ORDER = [
    ("Креативи та воронки", "🎯"),
    ("Перформанс та закупівля", "📊"),
    ("Тренди EdTech", "📈"),
    ("Кейси та цифри", "💡"),
]

_MONTHS_UA = [
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
]


def _human_date(dt: datetime) -> str:
    return f"{dt.day} {_MONTHS_UA[dt.month - 1]}"


def _emoji_for(category: str) -> str:
    for name, emoji in _CATEGORY_ORDER:
        if name.lower() == category.lower():
            return emoji
    return "📰"


def format_digest(
    entries: list[DigestEntry],
    evergreen: list[dict],
    now: datetime,
) -> str:
    parts: list[str] = []
    parts.append(f"<b>📬 EdTech Marketing Digest · {_human_date(now)}</b>")

    if entries:
        # группируем по категориям в заданном порядке
        grouped: dict[str, list[DigestEntry]] = {}
        for e in entries:
            grouped.setdefault(e.category, []).append(e)

        ordered_cats = [c for c, _ in _CATEGORY_ORDER if c in grouped]
        # категории, которых нет в списке порядка, — в конец
        ordered_cats += [c for c in grouped if c not in ordered_cats]

        idx = 1
        for cat in ordered_cats:
            parts.append("")
            parts.append(f"<b>{_emoji_for(cat)} {escape(cat.upper())}</b>")
            for e in grouped[cat]:
                title = escape(e.title)
                summary = escape(e.summary)
                src = escape(e.source)
                parts.append(
                    f'{idx}. <a href="{escape(e.url, quote=True)}"><b>{title}</b></a>\n'
                    f"{summary}\n"
                    f"<i>{src}</i>"
                )
                idx += 1
    else:
        parts.append("")
        parts.append("<i>Сьогодні вартих новин не знайшлося — рідкісний тихий день. "
                     "Зате нижче є вічна класика 👇</i>")

    if evergreen:
        parts.append("")
        parts.append("<b>♻️ ВІЧНОЗЕЛЕНЕ · КЛАСИКА ІНФОБІЗУ</b>")
        for ins in evergreen:
            principle = escape(ins.get("principle", ""))
            source = escape(ins.get("source", ""))
            insight = escape(ins.get("insight", ""))
            application = escape(ins.get("application", ""))
            block = f"<b>{principle}</b> — <i>{source}</i>\n{insight}"
            if application:
                block += f"\n\n👉 <b>Як застосувати:</b> {application}"
            parts.append(block)

    return "\n".join(parts)
