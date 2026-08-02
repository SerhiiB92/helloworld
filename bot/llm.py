"""LLM-слой: отбор релевантного и саммари на украинском языке.

Провайдер выбирается переменной LLM_PROVIDER:
  * "gemini" — Google Gemini (бесплатный тариф AI Studio), основной вариант;
  * "groq"   — Groq (бесплатный тариф, Llama 3.3), запасной вариант.

Оба вызываются напрямую по REST через httpx — без тяжёлых SDK.
Если основной провайдер падает, а ключ Groq задан, пробуем Groq.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time

import httpx

from config import Config
from models import DigestEntry, Item
from profile import Profile

log = logging.getLogger("llm")

_HTTP_TIMEOUT = 90.0

# Шаблон системного промпта для отбора новостей. Нишевые части (ниша, что доносит
# саммари, список категорий) подставляются из профиля.
_SYSTEM_PROMPT_TMPL = """Ти — редактор щоденного дайджесту з {niche}.
Тобі дають список кандидатів (статті, пости, відео) за останні добу-дві.
Твоє завдання — відібрати лише найцінніше, прибрати дублі та слабке, і по кожному
відібраному написати короткий підсумок УКРАЇНСЬКОЮ мовою.

Поверни СТРОГО валідний JSON без пояснень, у форматі:
{{"entries": [
  {{"id": "<id кандидата>",
   "title_ua": "<короткий заголовок українською>",
   "summary_ua": "<3-4 повних інформативних речення>",
   "category": "<одна з: {categories}>"}}
]}}

Вимоги до summary_ua (найважливіше):
- 3-4 ПОВНИХ речення, а не одне-два.
- Додай КОНКРЕТИКУ з тексту новини: що саме сталося, хто/яка компанія, цифри
  (суми, відсотки, дати), деталі, наслідки. НЕ переказуй лише заголовок.
- Поясни, {summary_hint}.
- Якщо у вихідному тексті мало деталей — усе одно витисни максимум суті, але
  не вигадуй фактів, яких немає.
- Українською, живо та змістовно, без markdown.

Інші правила:
- Не більше {max_items} записів. Тримай високий поріг якості.
- Якщо з кількох кандидатів це одна й та сама новина — залиш один найкращий.
- id бери РІВНО з поля id кандидата, нічого не вигадуй.
- Якщо нічого вартого немає — поверни {{"entries": []}}."""


def _build_system_prompt(profile: Profile, max_items: int) -> str:
    return _SYSTEM_PROMPT_TMPL.format(
        niche=profile.system_niche,
        summary_hint=profile.summary_hint,
        categories=" | ".join(profile.category_names()),
        max_items=max_items,
    )


def _extract_json(text: str) -> dict:
    """Достаёт JSON из ответа модели, даже если он обёрнут в ```json ... ```."""
    text = text.strip()
    # срезаем markdown-ограждение, если есть
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        # берём от первой { до последней }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    return json.loads(text)


def _build_user_prompt(criteria: str, candidates: list[dict]) -> str:
    payload = json.dumps(candidates, ensure_ascii=False, indent=1)
    return (
        f"{criteria}\n\n"
        f"Вот кандидаты (JSON-массив):\n{payload}\n\n"
        "Отбери лучшее и верни JSON в требуемом формате."
    )


def _call_gemini(cfg: Config, system: str, user: str, model: str | None = None) -> str:
    model = model or cfg.gemini_model
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        },
    }
    resp = httpx.post(
        url,
        params={"key": cfg.gemini_api_key},
        json=body,
        timeout=_HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_groq(cfg: Config, system: str, user: str) -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"
    body = {
        "model": cfg.groq_model,
        "temperature": 0.4,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {cfg.groq_api_key}"},
        json=body,
        timeout=_HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


# Коды, при которых имеет смысл подождать и повторить (временные лимиты/сбои).
_RETRYABLE = {429, 500, 502, 503, 504}


def _call_with_retry(label: str, callfn, system: str, user: str, attempts: int = 2) -> str:
    """Повторяет один вызатель при 429/5xx с экспоненциальной паузой.

    429 у бесплатного тарифа Gemini часто временный (лимит в минуту) — короткая
    пауза обычно его снимает. Задача суточная, так что подождать не страшно.
    """
    delay = 15.0
    for attempt in range(1, attempts + 1):
        try:
            return callfn(system, user)
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code in _RETRYABLE and attempt < attempts:
                retry_after = exc.response.headers.get("retry-after")
                try:
                    wait = float(retry_after) if retry_after else delay
                except ValueError:
                    wait = delay
                wait = min(wait, 60.0)
                log.warning(
                    "%s вернул %s — жду %.0fс и повторяю (%d/%d)",
                    label, code, wait, attempt, attempts,
                )
                time.sleep(wait)
                delay *= 2
                continue
            raise


def _gemini_models(cfg: Config) -> list[str]:
    """Основная модель Gemini + запасные (без дублей)."""
    models = [cfg.gemini_model]
    for m in cfg.gemini_fallback_models:
        if m and m not in models:
            models.append(m)
    return models


def _build_attempts(cfg: Config) -> list[tuple]:
    """Упорядоченный список попыток (label, callfn) по провайдерам/моделям."""
    attempts: list[tuple] = []

    def add_gemini():
        if not cfg.gemini_api_key:
            return
        for m in _gemini_models(cfg):
            attempts.append((f"gemini/{m}", lambda s, u, mm=m: _call_gemini(cfg, s, u, mm)))

    def add_groq():
        if cfg.groq_api_key:
            attempts.append(("groq", lambda s, u: _call_groq(cfg, s, u)))

    # Порядок задаёт llm_provider; другой провайдер идёт резервом.
    if cfg.llm_provider == "groq":
        add_groq()
        add_gemini()
    else:
        add_gemini()
        add_groq()
    return attempts


def _raw_call(cfg: Config, system: str, user: str) -> str:
    """Перебираем модели Gemini и провайдеров по очереди, каждую — с ретраями."""
    attempts = _build_attempts(cfg)
    if not attempts:
        raise RuntimeError("Не настроен ни один LLM-провайдер (нет ключей)")

    last_err: Exception | None = None
    for label, callfn in attempts:
        try:
            return _call_with_retry(label, callfn, system, user)
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            log.warning("%s не ответил: %s", label, exc)
            last_err = exc
    raise RuntimeError(f"Все LLM-варианты недоступны: {last_err}")


def select_and_summarize(cfg: Config, candidates: list[dict], profile: Profile) -> list[DigestEntry]:
    """Главная функция: из кандидатов выбираем топ и получаем саммари на украинском."""
    if not candidates:
        return []

    system = _build_system_prompt(profile, cfg.max_items)
    user = _build_user_prompt(profile.criteria, candidates)

    raw = _raw_call(cfg, system, user)
    try:
        parsed = _extract_json(raw)
    except json.JSONDecodeError as exc:
        log.error("LLM вернул невалидный JSON: %s\nОтвет: %s", exc, raw[:1000])
        return []

    by_id = {c["id"]: c for c in candidates}
    entries: list[DigestEntry] = []
    for e in parsed.get("entries", [])[: cfg.max_items]:
        cand = by_id.get(e.get("id"))
        if cand is None:
            # модель могла слегка исказить id — пропускаем, чтобы не давать битую ссылку
            continue
        entries.append(
            DigestEntry(
                title=(e.get("title_ua") or cand["title"]).strip(),
                summary=(e.get("summary_ua") or "").strip(),
                category=(e.get("category") or profile.default_category).strip(),
                url=cand["url"],
                source=cand["source"],
            )
        )
    log.info("LLM отобрал %d записей из %d кандидатов", len(entries), len(candidates))
    return entries


def fallback_entries(items: list[Item], limit: int, default_category: str) -> list[DigestEntry]:
    """Сырой список новостей БЕЗ обработки LLM — на случай, когда ИИ недоступен.

    Лучше отдать пользователю топ свежих ссылок, чем 'ничего интересного',
    когда новости на самом деле есть.
    """
    out: list[DigestEntry] = []
    for it in items[:limit]:
        text = (it.summary or "").strip().replace("\n", " ")
        if len(text) > 240:
            text = text[:240] + "…"
        out.append(
            DigestEntry(
                title=it.title.strip()[:200] or it.source,
                summary=text,
                category=default_category,
                url=it.url,
                source=it.source,
            )
        )
    return out


# --- Живые примеры для «вечнозелёных» инсайтов -----------------------------


def illustrate_evergreen(cfg: Config, insights: list[dict], profile: Profile) -> dict[str, str]:
    """Для каждого инсайта генерирует живой пример под конкретную нишу.

    Промпт и список ниш берутся из профиля. Возвращает {id: текст примера};
    при любой ошибке — пустой словарь (formatter покажет статичное application).
    """
    if not insights or not profile.illustrate_system or not profile.niches:
        return {}

    niches = random.sample(profile.niches, k=min(len(insights), len(profile.niches)))
    payload = []
    for i, ins in enumerate(insights):
        payload.append({
            "id": ins.get("id"),
            "principle": ins.get("principle", ""),
            "insight": ins.get("insight", ""),
            "niche": niches[i % len(niches)],
        })

    user = (
        "Ось принципи (JSON-масив). Для кожного напиши приклад у вказаній ніші:\n"
        + json.dumps(payload, ensure_ascii=False, indent=1)
    )

    try:
        raw = _raw_call(cfg, profile.illustrate_system, user)
        parsed = _extract_json(raw)
    except (RuntimeError, json.JSONDecodeError) as exc:
        log.warning("Не удалось сгенерировать примеры для классики: %s", exc)
        return {}

    result: dict[str, str] = {}
    for e in parsed.get("examples", []):
        eid = e.get("id")
        example = (e.get("example") or "").strip()
        if eid and example:
            result[eid] = example
    log.info("Сгенерировано %d примеров для классики", len(result))
    return result
