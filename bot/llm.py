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
import re

import httpx

from config import Config
from models import DigestEntry

log = logging.getLogger("llm")

_HTTP_TIMEOUT = 90.0

# Критерії релевантності — серце «розумного» відбору. Змінюючи цей текст,
# ви змінюєте смак бота.
CRITERIA = """Ніша: маркетинг в EdTech (онлайн-освіта), ринки Заходу та СНД.
Відбирай записи, корисні практикуючому маркетологу онлайн-школи за темами:
1. КРЕАТИВИ ТА ВОРОНКИ — нові підходи в креативах, лендінги, воронки, офери, запуски.
2. ПЕРФОРМАНС ТА ЗАКУПІВЛЯ — таргетинг, метрики, платформи (Meta/Google/TikTok), оптимізація ROI/CAC.
3. ТРЕНДИ EDTECH — новини індустрії, раунди, AI в освіті, рухи конкурентів.
4. КЕЙСИ ТА ЦИФРИ — конкретні розбори з метриками, A/B-тести, growth-кейси.
Відсіюй: загальні мотиваційні пости, рекламу без користі, клікбейт, дублі однієї новини,
новини поза нішею освіти/маркетингу."""

_SYSTEM_PROMPT = """Ти — редактор щоденного дайджесту з маркетингу в EdTech.
Тобі дають список кандидатів (статті, пости, відео) за останні добу-дві.
Твоє завдання — відібрати лише найцінніше, прибрати дублі та слабке, і по кожному
відібраному написати короткий підсумок УКРАЇНСЬКОЮ мовою.

Поверни СТРОГО валідний JSON без пояснень, у форматі:
{"entries": [
  {"id": "<id кандидата>",
   "title_ua": "<короткий заголовок українською>",
   "summary_ua": "<2-3 речення: суть і чим корисно маркетологу онлайн-школи>",
   "category": "<одна з: Креативи та воронки | Перформанс та закупівля | Тренди EdTech | Кейси та цифри>"}
]}

Правила:
- Не більше %(max_items)d записів. Краще менше, але якісніше — тримай високий поріг.
- Якщо з кількох кандидатів це одна й та сама новина — залиш один найкращий.
- id бери РІВНО з поля id кандидата, нічого не вигадуй.
- summary_ua пиши українською, живо та по суті, без води й без markdown.
- Якщо нічого вартого немає — поверни {"entries": []}."""


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


def _build_user_prompt(candidates: list[dict]) -> str:
    payload = json.dumps(candidates, ensure_ascii=False, indent=1)
    return (
        f"{CRITERIA}\n\n"
        f"Вот кандидаты (JSON-массив):\n{payload}\n\n"
        "Отбери лучшее и верни JSON в требуемом формате."
    )


def _call_gemini(cfg: Config, system: str, user: str) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{cfg.gemini_model}:generateContent"
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


def _raw_call(cfg: Config, system: str, user: str) -> str:
    """Зовём выбранный провайдер, при ошибке — fallback на Groq (если есть ключ)."""
    providers = [cfg.llm_provider]
    if cfg.llm_provider != "groq" and cfg.groq_api_key:
        providers.append("groq")

    last_err: Exception | None = None
    for provider in providers:
        try:
            if provider == "gemini":
                return _call_gemini(cfg, system, user)
            if provider == "groq":
                log.info("Использую LLM-провайдер: groq")
                return _call_groq(cfg, system, user)
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            log.warning("Провайдер %s не ответил: %s", provider, exc)
            last_err = exc
    raise RuntimeError(f"Все LLM-провайдеры недоступны: {last_err}")


def select_and_summarize(cfg: Config, candidates: list[dict]) -> list[DigestEntry]:
    """Главная функция: из кандидатов выбираем топ и получаем саммари на украинском."""
    if not candidates:
        return []

    system = _SYSTEM_PROMPT % {"max_items": cfg.max_items}
    user = _build_user_prompt(candidates)

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
                category=(e.get("category") or "Тренди EdTech").strip(),
                url=cand["url"],
                source=cand["source"],
            )
        )
    log.info("LLM отобрал %d записей из %d кандидатов", len(entries), len(candidates))
    return entries
