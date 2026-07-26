# 📬 EdTech Marketing Digest Bot

Телеграм-бот, который **раз в день в 10:00 по Варшаве** присылает вам:

1. **Дайджест новостей** (топ 5–7) по маркетингу в нише EdTech — креативы и
   воронки, перформанс и закуп, тренды рынка, кейсы с цифрами. Источники:
   зарубежные блоги/медиа (RSS) + публичные Telegram-каналы + YouTube.
   Отбор, дедупликацию и саммари на украинском делает LLM.
2. **1–2 «вечнозелёных» инсайта** из классики инфобиза — Хормози, «Запуск»
   Джеффа Уокера, Расселл Брансон, Чалдини и др. Бот ротирует их без повторов.

Работает на **бесплатных** сервисах: GitHub Actions (хостинг по расписанию) +
Google Gemini (бесплатный тариф). Ни своего сервера, ни платного API не нужно.

---

## 🏗 Как это устроено

```
GitHub Actions (cron)
  → collector.py   собирает записи из RSS / Telegram / YouTube за 48 ч
  → state.py       выкидывает уже присланные (антидубли)
  → llm.py         Gemini отбирает топ, дедуплицирует, пишет саммари на украинском
  → evergreen.py   достаёт 1–2 непоказанных инсайта из evergreen.json
  → formatter.py   собирает красивый HTML-дайджест
  → telegram_sender.py  шлёт вам в Telegram
  → коммитит state.json обратно в репозиторий (чтобы помнить историю)
```

| Файл | Назначение |
|---|---|
| `main.py` | оркестратор всего процесса |
| `config.py` | настройки из переменных окружения |
| `sources.yaml` | **список источников — правьте его под себя** |
| `evergreen.json` | **библиотека вечнозелёных инсайтов — пополняйте** |
| `collector.py` | сбор из RSS, Telegram (веб-превью), YouTube |
| `llm.py` | Gemini (осн.) / Groq (fallback) |
| `formatter.py` | вёрстка дайджеста |
| `telegram_sender.py` | отправка в Telegram |
| `state.py` | память между запусками (`state.json`) |

---

## 🚀 Запуск за 4 шага

### Шаг 1. Создать Telegram-бота и узнать свой chat_id

1. Напишите [@BotFather](https://t.me/BotFather) → `/newbot` → получите
   **`TELEGRAM_BOT_TOKEN`** (вида `123456:ABC-...`).
2. Напишите вашему новому боту любое сообщение (иначе он не сможет вам писать).
3. Узнайте свой **`TELEGRAM_CHAT_ID`**: напишите [@userinfobot](https://t.me/userinfobot)
   `/start` — он пришлёт ваш числовой id.

### Шаг 2. Получить бесплатный ключ Gemini

1. Откройте [Google AI Studio](https://aistudio.google.com/app/apikey) →
   **Create API key**. Карта не нужна.
2. Это ваш **`GEMINI_API_KEY`**. Бесплатного тарифа (сотни запросов в день)
   хватает с огромным запасом — бот делает ~1 запрос в день.

### Шаг 3. Прописать секреты в GitHub

В репозитории: **Settings → Secrets and variables → Actions → New repository secret**.
Добавьте:

| Secret | Значение |
|---|---|
| `TELEGRAM_BOT_TOKEN` | токен от BotFather |
| `TELEGRAM_CHAT_ID` | ваш id от userinfobot |
| `GEMINI_API_KEY` | ключ из AI Studio |
| `GROQ_API_KEY` | *(необязательно)* запасной провайдер, [console.groq.com](https://console.groq.com) |

*(Опционально)* на вкладке **Variables** можно переопределить настройки без
правки кода: `DIGEST_MAX_ITEMS`, `LOOKBACK_HOURS`, `EVERGREEN_COUNT`,
`TIMEZONE`, `TARGET_HOUR`, `LLM_PROVIDER`.

### Шаг 4. Включить расписание

Расписание в GitHub Actions запускается **только из ветки по умолчанию**
(обычно `main`). Смёржите эту ветку в `main` — и бот начнёт присылать дайджест
каждый день в 10:00 по Варшаве автоматически.

**Проверить прямо сейчас, не дожидаясь мёржа и утра:** вкладка **Actions →
EdTech Marketing Digest → Run workflow**. Поставьте галочку *dry-run*, чтобы
сделать тестовый прогон без отправки (результат — в логах), либо снимите её,
чтобы бот прислал реальный дайджест сразу.

---

## ⚙️ Настройка источников

Всё в `sources.yaml` — код трогать не нужно.

- **RSS** — добавляйте любые фиды блогов/медиа (`name` + `url`).
- **Telegram** — только **публичные каналы**, username без `@`. Обычных ботов
  (`*_bot`) читать нельзя — у них нет веб-превью.
- **YouTube** — нужен `channel_id` (строка `UC...`), не `@handle`. Как узнать —
  в комментариях внутри `sources.yaml`.

Недоступный источник бот просто пропускает — можно смело экспериментировать.

## 📚 Пополнение библиотеки классики

Добавляйте инсайты в `evergreen.json` в том же формате (`id`, `source`,
`principle`, `insight`, `application`). Бот подхватит их автоматически и
включит в ротацию.

---

## 🧪 Локальный запуск (для отладки)

```bash
cd bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# тестовый прогон без отправки — печатает дайджест в консоль
DRY_RUN=1 GEMINI_API_KEY=ваш_ключ python main.py

# боевой запуск с отправкой в Telegram
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... GEMINI_API_KEY=... python main.py
```

## 🔧 Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | токен бота (обязателен для отправки) |
| `TELEGRAM_CHAT_ID` | — | куда слать дайджест |
| `GEMINI_API_KEY` | — | ключ Gemini (при `LLM_PROVIDER=gemini`) |
| `LLM_PROVIDER` | `gemini` | `gemini` или `groq` |
| `GEMINI_MODEL` | `gemini-2.0-flash` | модель Gemini |
| `GROQ_API_KEY` | — | запасной провайдер |
| `DIGEST_MAX_ITEMS` | `7` | максимум новостей в дайджесте |
| `LOOKBACK_HOURS` | `48` | за какой период собирать |
| `EVERGREEN_COUNT` | `2` | сколько инсайтов классики в день |
| `TIMEZONE` | `Europe/Warsaw` | часовой пояс |
| `TARGET_HOUR` | — | локальный час отправки (защита от перевода часов) |
| `DRY_RUN` | — | `1` = не отправлять, печатать в консоль |
