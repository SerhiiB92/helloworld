"""Ротация вечнозелёных инсайтов из классики инфобиза.

Читаем библиотеку из evergreen.json и выбираем N ещё не показанных инсайтов.
Когда весь пул показан — State сам сбрасывает цикл, и ротация начинается заново.
"""

from __future__ import annotations

import json
import logging
import random

from state import State

log = logging.getLogger("evergreen")


def load_library(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("insights", []))


def pick_evergreen(library: list[dict], state: State, count: int) -> list[dict]:
    """Возвращает до `count` ещё не показанных инсайтов (перемешанных)."""
    if not library or count <= 0:
        return []

    seen = set(state.seen_evergreen)
    unseen = [x for x in library if x.get("id") not in seen]

    # если непоказанных не хватает — добираем из всех (цикл всё равно скоро сбросится)
    pool = unseen if len(unseen) >= count else library

    random.shuffle(pool)
    chosen = pool[:count]
    log.info("Вечнозелёное: выбрано %d инсайтов (непоказанных было %d)", len(chosen), len(unseen))
    return chosen
