"""Вёрстка дайджеста в HTML для Telegram.

Telegram поддерживает ограниченный HTML (parse_mode=HTML). Используем его,
потому что он надёжнее Markdown в плане экранирования спецсимволов.
Нишевые части (заголовок, категории, шапка классики) берутся из профиля.
"""

from __future__ import annotations

from datetime import datetime
from html import escape

from models import DigestEntry
from profile import Profile

_MONTHS_UA = [
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
]


def _human_date(dt: datetime) -> str:
    return f"{dt.day} {_MONTHS_UA[dt.month - 1]}"


def format_digest(
    entries: list[DigestEntry],
    evergreen: list[dict],
    now: datetime,
    profile: Profile,
    degraded: bool = False,
) -> str:
    category_order = profile.categories  # list of (name, emoji)
    emoji_by_cat = {name.lower(): emoji for name, emoji in category_order}

    parts: list[str] = []
    parts.append(f"<b>📬 {escape(profile.title)} · {_human_date(now)}</b>")

    if degraded and entries:
        # ИИ был недоступен — предупреждаем, что это сырой список без обработки.
        parts.append("")
        parts.append("<i>⚠️ ШІ тимчасово недоступний (ліміт). Нижче — сирий список "
                     "свіжих матеріалів без відбору й підсумків.</i>")

    if entries:
        grouped: dict[str, list[DigestEntry]] = {}
        for e in entries:
            grouped.setdefault(e.category, []).append(e)

        ordered_cats = [name for name, _ in category_order if name in grouped]
        # категории, которых нет в списке порядка, — в конец
        ordered_cats += [c for c in grouped if c not in ordered_cats]

        idx = 1
        for cat in ordered_cats:
            emoji = emoji_by_cat.get(cat.lower(), "📰")
            parts.append("")
            parts.append(f"<b>{emoji} {escape(cat.upper())}</b>")
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
        parts.append("<i>Сьогодні вартих новин не знайшлося — рідкісний тихий день.</i>")

    if evergreen:
        parts.append("")
        parts.append(f"<b>{escape(profile.evergreen_header)}</b>")
        for ins in evergreen:
            principle = escape(ins.get("principle", ""))
            source = escape(ins.get("source", ""))
            insight = escape(ins.get("insight", ""))
            block = f"<b>{principle}</b> — <i>{source}</i>\n{insight}"
            # Живой пример под нишу (сгенерирован LLM); запасной — статичное application.
            example = ins.get("example") or ins.get("application", "")
            if example:
                block += f"\n\n📎 <b>{escape(profile.example_label)}:</b> {escape(example)}"
            parts.append(block)

    return "\n".join(parts)
