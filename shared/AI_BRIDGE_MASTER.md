# AI-Bridge — Мастер-инструкция
> Версия: 2026-05-17 | Агенты: Claude Desktop · Qwen Chat · Gemini CLI · Qwen CLI · Hermes

---

## Архитектура системы

```
┌─────────────────────────────────────────────────────┐
│           ОРКЕСТРАТОРЫ (первичные)                  │
│   Claude Desktop          Qwen Chat                 │
│   (ai-bridge MCP)         (ai-bridge MCP)           │
└──────────────────┬──────────────────────────────────┘
                   │ run_gemini / run_qwen / run_hermes
         ┌─────────▼──────────────────────┐
         │        AI-BRIDGE MCP           │
         │  shared/  ← общая папка        │
         └────┬──────────┬───────────┬───┘
              ▼          ▼           ▼
         Gemini CLI   Qwen CLI    Hermes
         (субагент)  (субагент)  (субагент)
```

**Каждый агент может опционально стать оркестратором** — делегировать задачи другим через те же инструменты.

---

## Роли агентов

| Агент | Основная роль | Вызов через bridge | Может оркестрировать |
|-------|--------------|-------------------|----------------------|
| **Claude Desktop** | Оркестратор | — (сам вызывает) | ✅ Всегда |
| **Qwen Chat** | Оркестратор | — (сам вызывает) | ✅ Всегда |
| **Gemini CLI** | Субагент-исполнитель | `run_gemini()` | ✅ Опционально |
| **Qwen CLI** | Субагент-исполнитель | `run_qwen()` | ✅ Опционально |
| **Hermes** | Субагент-исполнитель | `run_hermes()` | ✅ Опционально |

> ⚠️ **Qwen Chat ≠ Qwen CLI**
> - **Qwen Chat** — десктопное приложение, оркестратор. Вызвать его через bridge **нельзя**.
> - **Qwen CLI** — командная строка, субагент. Вызывается через `run_qwen()`.

---

## ШАГ 0 — ОБЯЗАТЕЛЬНО в начале любой сессии

Перед делегированием задач — проверить связь:

```
run_gemini("ping")  → ожидать любой текстовый ответ
run_qwen("ping")    → ожидать любой текстовый ответ
run_hermes("ping")  → ожидать любой текстовый ответ
```

- Недоступных агентов — пометить, не делегировать им
- Повторить ping через 30 сек (1 попытка)
- Если агент недоступен — использовать следующего по приоритету

---

## Правила при ошибках (для всех агентов)

| Ошибка | Действие |
|--------|----------|
| **Rate Limit / 429** | Переключить модель вниз по таблице fallback → подождать 15–30 сек → повторить |
| **Timeout** | Упростить промпт (< 80 слов), разбить задачу → повторить |
| **Connection closed / MCP error** | Подождать 10 сек → повторить до 3 раз |
| **Empty response** | Повторить с более коротким промптом, сменить модель |
| **Auth error** | Проверить ключ API, сообщить пользователю |

**Максимум 3 попытки → затем передать следующему агенту или выполнить самому.**

---

## Gemini CLI — модели и fallback

| # | Модель |
|---|--------|
| 1 | `gemini-3.1-pro-preview` |
| 2 | `gemini-3-flash-preview` |
| 3 | `gemini-3.1-flash-lite-preview` |

**Вызов:** `run_gemini(prompt, use_tools=False/True)`
- `use_tools=False` — генерация текста/кода. Промпт **< 150 слов**.
- `use_tools=True` — shell/PowerShell команды. **НЕ** для записи файлов.

---

## Qwen CLI — модели и fallback

| # | Модель |
|---|--------|
| 1 | `qwen3.6-plus` |
| 2 | `deepseek-v4-pro` |
| 3 | `glm-5.1` |
| 4 | `deepseek-v4-flash` |

**Вызов:** `run_qwen(prompt)` — всегда с `--yolo`, доступ к shell.
- Промпт **< 100 слов**.
- Всегда указывать **абсолютный путь** к файлу.
- Пишет файлы напрямую по абсолютному пути.

---

## Hermes — модели и fallback

| # | Модель |
|---|--------|
| 1 | `openai/gpt-oss-120b:free` ← текущая |
| 2 | `nvidia/nemotron-3-super-120b-a12b:free` |
| 3 | ~~`z-ai/glm-4.5-air:free`~~ (timeout) |
| 4 | ~~`deepseek/deepseek-v4-flash:free`~~ (timeout) |

**Вызов:** `run_hermes(prompt)` — non-interactive, `--yolo`.
- Промпт **< 120 слов**.
- Имеет shell, файлы, persistent memory, skills.
- Смена модели: `C:\Users\almax\hermes-agent\cli-config.yaml` → `model.default`

---

## Матрица делегирования

| Задача | Приоритет агентов |
|--------|------------------|
| Генерация кода / текста | Gemini (`use_tools=False`) → Hermes → Qwen CLI |
| Запись файлов | Qwen CLI (абс. путь) → Hermes |
| Shell / pip / логи | Gemini (`use_tools=True`) → Qwen CLI |
| Многошаговые + memory | Hermes → Gemini |
| Интернет / поиск | Gemini (`use_tools=True`) → Hermes |
| Резерв (всё недоступно) | Оркестратор выполняет сам |

---

## Shared папка для обмена данными

```
C:\Users\almax\ai-bridge\shared\
├── AI_BRIDGE_MASTER.md         ← этот файл
├── CLAUDE_DELEGATION_RULES.md  ← для Claude Desktop
├── QWEN_CHAT_INSTRUCTIONS.md   ← для Qwen Chat
├── GEMINI_INSTRUCTIONS.md      ← для Gemini CLI
├── QWEN_CLI_INSTRUCTIONS.md    ← для Qwen CLI
├── HERMES_INSTRUCTIONS.md      ← для Hermes
├── claude_inbox.txt            ← задачи для Claude
└── [agent]_[task].txt          ← промежуточные результаты
```
