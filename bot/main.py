"""Точка входа: собрать → отфильтровать → обработать LLM → отправить дайджест.

Запуск локально (без отправки, печать в консоль):
    DRY_RUN=1 GEMINI_API_KEY=... python main.py

Запуск боевой (отправка в Telegram):
    TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... GEMINI_API_KEY=... python main.py

В GitHub Actions все переменные приходят из Secrets.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import collector
import evergreen as evergreen_mod
import llm
from config import load_config
from formatter import format_digest
from state import State
from telegram_sender import send_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")

_HERE = os.path.dirname(os.path.abspath(__file__))
_SOURCES_PATH = os.path.join(_HERE, "sources.yaml")
_EVERGREEN_PATH = os.path.join(_HERE, "evergreen.json")
_STATE_PATH = os.path.join(_HERE, "state.json")


def run() -> int:
    cfg = load_config()

    problems = cfg.validate_for_send()
    if problems:
        for p in problems:
            log.error("Конфигурация: %s", p)
        log.error("Прерываю запуск. Задайте недостающие переменные окружения / Secrets.")
        return 1

    tz = ZoneInfo(cfg.timezone)
    now = datetime.now(tz)
    today = now.date().isoformat()

    state = State(_STATE_PATH)

    # Расписание: слать максимум раз в день, при первом запуске В или ПОСЛЕ
    # целевого часа. Так задержки GitHub-крона (иногда 30-60+ мин) не роняют
    # день — раньше строгая проверка "час == 10" могла молча пропустить сутки.
    # dry-run проверку не трогает: даёт тестировать в любое время.
    if cfg.target_hour is not None and not cfg.dry_run:
        if state.last_sent_date == today:
            log.info("Сегодня (%s) дайджест уже отправляли — пропускаю.", today)
            return 0
        if now.hour < cfg.target_hour:
            log.info(
                "Ещё рано: %02d:00 по %s, целевой час — %02d:00. Ждём следующий запуск.",
                now.hour, cfg.timezone, cfg.target_hour,
            )
            return 0

    # 1. Сбор
    sources = collector.load_sources(_SOURCES_PATH)
    items = collector.collect_all(sources, cfg.lookback_hours)
    log.info("Всего собрано записей: %d", len(items))

    # 2. Отсев уже присланных
    fresh = [it for it in items if not state.is_news_seen(it.uid)]
    log.info("Новых (не присланных ранее): %d", len(fresh))

    # 3. LLM: отбор + саммари
    #    Каналов/источников много — ограничиваем число кандидатов, отдавая
    #    приоритет самым свежим, чтобы один LLM-запрос оставался компактным.
    entries = []
    degraded = False  # True, если ИИ недоступен и шлём сырой список
    if fresh:
        fresh_sorted = sorted(
            fresh,
            key=lambda it: it.published or datetime.min.replace(tzinfo=tz),
            reverse=True,
        )
        candidates = [it.to_candidate() for it in fresh_sorted[: cfg.max_candidates]]
        log.info("Кандидатов передаём в LLM: %d (из %d свежих)", len(candidates), len(fresh))
        try:
            entries = llm.select_and_summarize(cfg, candidates)
        except Exception as exc:  # noqa: BLE001 - не хотим падать без дайджеста
            log.error("LLM-обработка не удалась: %s", exc)
            # ИИ недоступен, но новости есть — отдаём сырой топ вместо пустоты.
            entries = llm.fallback_entries(fresh_sorted, cfg.max_items)
            degraded = True
            log.info("Отправляю сырой fallback: %d записей", len(entries))

    # 4. Вечнозелёные инсайты + живые примеры под нишу
    library = evergreen_mod.load_library(_EVERGREEN_PATH)
    evergreen_items = evergreen_mod.pick_evergreen(library, state, cfg.evergreen_count)
    if evergreen_items:
        try:
            examples = llm.illustrate_evergreen(cfg, evergreen_items)
            for ins in evergreen_items:
                if ins.get("id") in examples:
                    ins["example"] = examples[ins["id"]]
        except Exception as exc:  # noqa: BLE001 - примеры необязательны
            log.warning("Генерация примеров для классики не удалась: %s", exc)

    # Если нет вообще ничего — не отправляем пустышку
    if not entries and not evergreen_items:
        log.info("Нечего отправлять сегодня. Завершаю без сообщения.")
        state.save()
        return 0

    # 5. Вёрстка
    message = format_digest(entries, evergreen_items, now, degraded=degraded)

    # 6. Отправка
    if cfg.dry_run:
        print("\n" + "=" * 70)
        print("DRY RUN — сообщение не отправлено. Вот что ушло бы в Telegram:\n")
        print(message)
        print("=" * 70 + "\n")
    else:
        send_message(cfg.telegram_bot_token, cfg.telegram_chat_id, message)
        log.info("Дайджест отправлен в Telegram (chat_id=%s)", cfg.telegram_chat_id)
        # Отмечаем дату отправки — чтобы следующий запуск в тот же день не дублировал.
        state.last_sent_date = today

    # 7. Обновление состояния
    #    Помечаем присланные новости и показанные инсайты, чтобы не повторяться.
    shown_urls = {e.url for e in entries}
    state.mark_news([it.uid for it in fresh if it.url in shown_urls])
    state.mark_evergreen([x["id"] for x in evergreen_items], total_available=len(library))
    state.save()

    return 0


if __name__ == "__main__":
    sys.exit(run())
