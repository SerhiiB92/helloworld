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

log = logging.getLogger("llm")

_HTTP_TIMEOUT = 90.0

# Критерії релевантності — серце «розумного» відбору. Змінюючи цей текст,
# ви змінюєте смак бота.
CRITERIA = """Ніша: маркетинг в EdTech (онлайн-освіта), ринки Заходу та СНД.
Відбирай записи, корисні практикуючому маркетологу онлайн-школи за темами:
1. КРЕАТИВИ ТА ВОРОНКИ — нові підходи в креативах, лендінги, воронки, офери, запуски.
2. ПЕРФОРМАНС ТА ЗАКУПІВЛЯ — таргетинг, метрики, платформи (Meta/Google/TikTok), UA, оптимізація ROI/CAC.
3. ТРЕНДИ EDTECH — новини індустрії, раунди, AI в освіті, рухи конкурентів.
4. КЕЙСИ ТА ЦИФРИ — конкретні розбори з метриками, A/B-тести, growth-кейси.

Джерела ширші за суто EdTech: серед них канали про закупівлю трафіку, UA,
мобільні підписки, growth, AI-інструменти для продакшну креативів та досвід
фаундерів. Це нормально — бери з них те, що маркетолог онлайн-школи може
ЗАСТОСУВАТИ (тактика, механіка воронки, підхід до креативів, монетизація
підписок, новий AI-інструмент для реклами), і в підсумку коротко поясни, як
саме це застосувати в онлайн-освіті. Загальні новини не з маркетингу — відсіюй.

Відсіюй: загальні мотиваційні/філософські пости, рекламу без користі, клікбейт,
дублі однієї новини, суто особисті нотатки, новини поза темою маркетингу."""

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


# Коды, при которых имеет смысл подождать и повторить (временные лимиты/сбои).
_RETRYABLE = {429, 500, 502, 503, 504}


def _call_one(provider: str, cfg: Config, system: str, user: str) -> str:
    if provider == "gemini":
        return _call_gemini(cfg, system, user)
    if provider == "groq":
        return _call_groq(cfg, system, user)
    raise RuntimeError(f"Неизвестный провайдер: {provider}")


def _call_with_retry(provider: str, cfg: Config, system: str, user: str, attempts: int = 3) -> str:
    """Повторяет запрос при 429/5xx с экспоненциальной паузой.

    429 у бесплатного тарифа Gemini часто временный (лимит в минуту) — короткая
    пауза обычно его снимает. Задача суточная, так что подождать не страшно.
    """
    delay = 15.0
    for attempt in range(1, attempts + 1):
        try:
            return _call_one(provider, cfg, system, user)
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
                    "Провайдер %s вернул %s — жду %.0fс и повторяю (%d/%d)",
                    provider, code, wait, attempt, attempts,
                )
                time.sleep(wait)
                delay *= 2
                continue
            raise


def _raw_call(cfg: Config, system: str, user: str) -> str:
    """Зовём выбранный провайдер (с ретраями), при ошибке — fallback на Groq."""
    providers = [cfg.llm_provider]
    if cfg.llm_provider != "groq" and cfg.groq_api_key:
        providers.append("groq")

    last_err: Exception | None = None
    for provider in providers:
        try:
            return _call_with_retry(provider, cfg, system, user)
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


# Эмодзи-категория по типу источника — для сырого fallback без LLM.
_TYPE_CATEGORY = {
    "telegram": "Тренди EdTech",
    "youtube": "Тренди EdTech",
    "rss": "Тренди EdTech",
}


def fallback_entries(items: list[Item], limit: int) -> list[DigestEntry]:
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
                category=_TYPE_CATEGORY.get(it.source_type, "Тренди EdTech"),
                url=it.url,
                source=it.source,
            )
        )
    return out


# --- Живые примеры для «вечнозелёных» инсайтов -----------------------------

# Конкретные ниши онлайн-образования. Каждый день выбираем случайные, чтобы
# примеры к классике не приедались и звучали свежо.
_NICHES = [
    "онлайн-курси англійської для дорослих",
    "IT-буткемп з програмування для новачків",
    "підготовка школярів до НМТ/ЗНО",
    "онлайн-школа малювання та ілюстрації",
    "курси Figma та UX/UI-дизайну",
    "дитяча онлайн-школа математики",
    "курси іспанської з нуля",
    "онлайн-курси SMM та таргетингу",
    "школа гри на гітарі онлайн",
    "курси Excel та аналітики даних",
    "онлайн-марафон з йоги та фітнесу",
    "курси копірайтингу та контент-маркетингу",
    "підготовка до IELTS/TOEFL онлайн",
    "школа програмування для дітей (Scratch/Python)",
]

_ILLUSTRATE_SYSTEM = """Ти — досвідчений маркетолог-практик в EdTech і сильний копірайтер.
Тобі дають список маркетингових принципів із класики інфобізу. До КОЖНОГО
напиши РОЗГОРНУТИЙ, дуже конкретний приклад застосування в ніші онлайн-освіти,
яку вказано в полі niche.

Приклад має бути НЕ абстрактним, а «бери й роби». Обовʼязково включи конкретику:
- персонаж і ситуація (напр. «Олена, засновниця школи іспанської»);
- якщо мова про оффер — напиши сам оффер дослівно (назва + що входить);
- якщо доречно — 2-4 конкретних БОНУСИ списком (напр. «розмовний клуб», «шаблони фраз», «перевірка вимови»);
- конкретні цифри: ціна, дедлайн, гарантія, метрика до/після (напр. «конверсія 3% → 7%»);
- за потреби — 2-3 практичних КРОКИ, що саме зробити.

Стиль: українською, живо й предметно, 4-7 речень. Можна використати короткий
список через тире всередині тексту. Без markdown-заголовків, без води.

Поверни СТРОГО валідний JSON без пояснень:
{"examples": [{"id": "<id принципу>", "example": "<розгорнутий конкретний приклад>"}]}"""


def illustrate_evergreen(cfg: Config, insights: list[dict]) -> dict[str, str]:
    """Для каждого инсайта генерирует живой пример под конкретную нишу.

    Возвращает {id: текст примера}. При любой ошибке — пустой словарь
    (в этом случае formatter покажет статичное поле application как запасной).
    """
    if not insights:
        return {}

    niches = random.sample(_NICHES, k=min(len(insights), len(_NICHES)))
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
        raw = _raw_call(cfg, _ILLUSTRATE_SYSTEM, user)
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
