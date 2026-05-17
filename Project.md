# AI-Bridge MCP — Проектная документация

> Версия: 1.0 | Дата: 2026-05-17
> Путь: `C:\Users\almax\ai-bridge\`
> Автор: almax + Claude Desktop

---

## 1. Концепция и назначение

**AI-Bridge** — MCP-сервер (Model Context Protocol), реализующий единую точку интеграции между пятью AI-агентами. Позволяет любому из агентов вызывать других, обмениваться данными через общую папку и строить многоагентные пайплайны без сложной инфраструктуры.

### Проблема, которую решает

Каждый AI-агент работает изолированно: Claude не может напрямую вызвать Gemini, Qwen Chat не может поставить задачу Hermes. AI-Bridge создаёт единый протокол коммуникации поверх MCP — стандарта, поддерживаемого всеми современными AI-инструментами.

### Ключевая идея

```
Любой агент → ai-bridge MCP → Любой другой агент
```

Вместо сложных API-интеграций — один Python-файл, запускаемый как MCP stdio-сервер.

---

## 2. Архитектура системы

### 2.1 Агенты и роли

```
┌─────────────────────────────────────────────────────────────┐
│                  ОРКЕСТРАТОРЫ (первичные)                   │
│                                                             │
│   Claude Desktop              Qwen Chat                     │
│   (MCP: claude_desktop)       (MCP: qwen_settings)          │
│   Anthropic Claude 4.x        Alibaba Qwen / DeepSeek       │
└──────────────────────┬──────────────────────────────────────┘
                       │
              ┌────────▼────────┐
              │   AI-BRIDGE MCP │  ← mcp-server.py (FastMCP)
              │  stdio transport│  ← Python 3.13
              │  8 инструментов │
              └───┬─────┬───┬───┘
                  │     │   │
         ┌────────▼─┐ ┌─▼──────┐ ┌──▼─────┐
         │Gemini CLI│ │Qwen CLI│ │ Hermes │
         │Node.js   │ │Node.js │ │Python  │
         │Google AI │ │Alibaba │ │OpenRtr │
         └──────────┘ └────────┘ └────────┘
```

| Агент | Тип | Вызов через bridge | Первичная роль |
|-------|-----|-------------------|----------------|
| Claude Desktop | Десктоп-приложение | — (сам вызывает) | Оркестратор |
| Qwen Chat | Десктоп-приложение | — (сам вызывает) | Оркестратор |
| Gemini CLI | CLI (Node.js) | `run_gemini()` | Субагент-исполнитель |
| Qwen CLI | CLI (Node.js) | `run_qwen()` | Субагент-исполнитель |
| Hermes Agent | CLI (Python) | `run_hermes()` | Субагент-исполнитель |

> Каждый агент может **опционально** выступать оркестратором — делегировать задачи другим.

### 2.2 Shared папка — шина данных

```
C:\Users\almax\ai-bridge\shared\
├── AI_BRIDGE_MASTER.md          ← единая инструкция для всех агентов
├── CLAUDE_DELEGATION_RULES.md   ← правила для Claude Desktop
├── QWEN_CHAT_INSTRUCTIONS.md    ← правила для Qwen Chat
├── GEMINI_INSTRUCTIONS.md       ← правила для Gemini CLI
├── QWEN_CLI_INSTRUCTIONS.md     ← правила для Qwen CLI
├── HERMES_INSTRUCTIONS.md       ← правила для Hermes
├── claude_inbox.txt             ← асинхронная очередь задач для Claude
├── claude_response*.txt         ← ответы Claude другим агентам
└── [agent]_[task].txt           ← промежуточные результаты
```

---

## 3. MCP-инструменты (API)

### 3.1 Полный список (8 инструментов)

| Инструмент | Параметры | Назначение |
|------------|-----------|-----------|
| `get_bridge_status` | — | Проверка работоспособности моста, наличия агентов |
| `run_gemini` | `prompt: str`, `use_tools: bool = False` | Вызов Gemini CLI |
| `run_qwen` | `prompt: str` | Вызов Qwen Code CLI |
| `run_hermes` | `prompt: str` | Вызов Hermes Agent |
| `save_to_shared` | `filename: str`, `content: str` | Запись файла в shared папку |
| `read_from_shared` | `filename: str` | Чтение файла из shared папки |
| `list_shared` | — | Список файлов в shared папке |
| `task_for_claude` | `task: str`, `from_agent: str` | Асинхронная постановка задачи Claude |

### 3.2 Детали реализации каждого инструмента

#### `run_gemini`
```python
cmd = [NODE_EXE, GEMINI_BUNDLE, "-p", prompt, "--skip-trust"]
# use_tools=True добавляет: "--yolo"
# Модель читается из ~/.gemini/settings.json
# cwd = shared/ (не git-репозиторий — отключает checkpointing)
# env: CI=true, NO_COLOR=1, GEMINI_DISABLE_CHECKPOINTING=true
# timeout: 120 сек
# Декодирование: UTF-8 + очистка ANSI-кодов
# Fallback stderr: cp1251 (Windows)
```

#### `run_qwen`
```python
cmd = [NODE_EXE, QWEN_BUNDLE, "-p", prompt, "--yolo"]
# NODE_EXE = абсолютный путь (не зависит от PATH subprocess)
# env: DASHSCOPE_API_KEY встроен, CI=true
# timeout: 180 сек
```

#### `run_hermes`
```python
cmd = [HERMES_EXE, "chat", "-q", prompt, "-Q", "--yolo"]
# -Q = quiet mode (только финальный ответ)
# cwd = C:\Users\almax\hermes-agent (читает .env и cli-config.yaml)
# env: OPENROUTER_API_KEY встроен
# timeout: 180 сек
```

#### `task_for_claude`
```python
# Append-режим — не перезаписывает, накапливает задачи
# Формат: [timestamp] FROM: agent_name \n task \n ---
# Claude периодически читает claude_inbox.txt и обрабатывает
```

---

## 4. Конфигурация агентов

### 4.1 Claude Desktop
```json
// %APPDATA%\Claude\claude_desktop_config.json
{
  "mcpServers": {
    "ai-bridge": {
      "command": "python",
      "args": ["C:\\Users\\almax\\ai-bridge\\mcp-server.py"]
    }
  }
}
```

### 4.2 Gemini CLI
```json
// C:\Users\almax\.gemini\settings.json
{
  "mcpServers": {
    "ai-bridge": {
      "command": "C:\\Users\\almax\\AppData\\Local\\Programs\\Python\\Python313\\python.exe",
      "args": ["C:\\Users\\almax\\ai-bridge\\mcp-server.py"]
    }
  },
  "model": { "name": "gemini-3.1-pro-preview" },
  "general": { "checkpointing": { "enabled": false } }
}
```

### 4.3 Qwen Chat / Desktop
```json
// %APPDATA%\Qwen\settings.json → mcp_config
{
  "ai-bridge": {
    "name": "ai-bridge",
    "command": "C:\\Program Files\\nodejs\\node.exe",
    "args": ["C:\\Users\\almax\\ai-bridge\\run-bridge.js"],
    "transportType": "stdio"
  }
}
```

### 4.4 Cline (VS Code)
```json
// globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json
{
  "ai-bridge": {
    "command": "python",
    "args": ["C:\\Users\\almax\\ai-bridge\\mcp-server.py"]
  }
}
```

### 4.5 Hermes Agent
```
// C:\Users\almax\hermes-agent\cli-config.yaml
model:
  default: "nvidia/nemotron-3-super-120b-a12b:free"
  provider: "openrouter"

// C:\Users\almax\hermes-agent\.env
OPENROUTER_API_KEY=sk-or-v1-...
```

---

## 5. Модели и провайдеры

### Gemini CLI — Google AI (бесплатно)
| # | Модель | Сила |
|---|--------|------|
| 1 | `gemini-3.1-pro-preview` | Основная |
| 2 | `gemini-3-flash-preview` | Fallback |
| 3 | `gemini-3.1-flash-lite-preview` | Быстрый fallback |

### Qwen CLI — Alibaba DashScope
| # | Модель | Сила |
|---|--------|------|
| 1 | `qwen3.6-plus` | Основная |
| 2 | `deepseek-v4-pro` | Fallback |
| 3 | `glm-5.1` | Fallback |
| 4 | `deepseek-v4-flash` | Быстрый fallback |

### Hermes — OpenRouter (бесплатные модели)
| # | Модель | Сила |
|---|--------|------|
| 1 | `openai/gpt-oss-120b:free` ← текущая | Основная |
| 2 | `nvidia/nemotron-3-super-120b-a12b:free` | Fallback |
| 3 | ~~`z-ai/glm-4.5-air:free`~~ (timeout) | Fallback |
| 4 | ~~`deepseek/deepseek-v4-flash:free`~~ (timeout) | Быстрый fallback |

---

## 6. Матрица делегирования задач

| Задача | Рекомендуемый агент | Почему |
|--------|---------------------|--------|
| Генерация кода | Gemini (`use_tools=False`) | Быстро, без shell |
| Запись файлов | Qwen CLI | Пишет по абс. пути напрямую |
| Shell / pip / логи | Gemini (`use_tools=True`) | Shell доступ через yolo |
| Многошаговые задачи | Hermes | Persistent memory + skills |
| Поиск в интернете | Gemini или Hermes | Оба имеют web доступ |
| Параллельные задачи | Gemini + Qwen одновременно | Независимые подзадачи |
| Асинхронно → Claude | `task_for_claude()` | Через inbox-файл |

---

## 7. Технические аспекты и решения

### 7.1 Транспорт: stdio (не HTTP)
MCP использует stdio как транспортный протокол — сервер читает JSON из stdin и пишет в stdout. Это означает:
- **stdout зарезервирован** для MCP-протокола — любой `print()` в начале скрипта ломает соединение
- FastMCP автоматически обрабатывает stdio-транспорт при `mcp.run()`
- Процесс запускается заново при каждом подключении клиента

### 7.2 Проблема PATH в subprocess
При запуске через MCP subprocess наследует минимальный PATH без `node.exe`, `git.exe` и системных утилит. Решение: **хардкод абсолютных путей**:
```python
NODE_EXE = r"C:\Program Files\nodejs\node.exe"
GEMINI_BUNDLE = r"C:\Users\almax\AppData\Roaming\npm\node_modules\@google\gemini-cli\bundle\gemini.js"
```

### 7.3 Проблема Gemini Checkpointing
Gemini CLI по умолчанию включает git-checkpointing — это вызывает ошибку в subprocess (нет git-репозитория). Решение:
```python
env["GEMINI_DISABLE_CHECKPOINTING"] = "true"
env["GEMINI_CLI_NO_CHECKPOINTING"] = "true"
cwd = str(SHARED_DIR)  # папка без .git
```
И в `~/.gemini/settings.json`:
```json
"checkpointing": { "enabled": false }
```

### 7.4 Кодировка на Windows
- Gemini выводит UTF-8; stderr может быть cp1251 — декодируем оба варианта
- ANSI-escape коды удаляются через regex: `re.sub(r'\x1b\[[0-9;]*[A-Za-zm]', '', output)`
- `CI=true` и `NO_COLOR=1` отключают цветной вывод большинства CLI

### 7.5 Hermes: quiet mode
Hermes по умолчанию выводит TUI/баннер. Флаги для subprocess:
```
hermes chat -q "промпт" -Q --yolo
# -q = single query (non-interactive)
# -Q = quiet (только финальный ответ + session_id в stderr)
# --yolo = bypass approval prompts
```

### 7.6 Асинхронная коммуникация через inbox
`task_for_claude()` реализует async pattern — агент кладёт задачу в файл, Claude читает при следующей активации. Это обходит ограничение: Claude нельзя вызвать синхронно через subprocess.

---

## 8. Шаги разработки (история)

### Этап 1 — Базовый мост (Mai 14, 2026)
- Создан `mcp-server.py` на FastMCP
- Реализованы `run_gemini`, `run_qwen`, `save_to_shared`, `read_from_shared`, `list_shared`
- Подключён к Claude Desktop и Gemini CLI

### Этап 2 — Отладка subprocess (Mai 14, 2026)
- Исправлена ошибка `node.exe not found` — захардкожен абсолютный путь
- Исправлен `--headless` флаг Gemini (не существует — вызывал зависание)
- Исправлена проблема git-checkpointing Gemini
- Исправлена аутентификация Qwen: `DASHSCOPE_API_KEY` в subprocess env

### Этап 3 — Многоагентная коммуникация (Mai 14, 2026)
- Добавлен `task_for_claude()` — асинхронная очередь задач
- Верифицирована полная матрица: Claude ↔ Gemini ↔ Qwen CLI ↔ Qwen Chat
- Тест: реальный запрос FIFA World Cup 2026 через цепочку агентов

### Этап 4 — Подключение Cline (Mai 16, 2026)
- ai-bridge добавлен в Cline (VS Code) MCP конфиг
- Отключён сломанный `browser-tools-mcp` (транспортные ошибки)
- Верифицирована двунаправленная коммуникация Cline ↔ Claude

### Этап 5 — Hermes Agent (Mai 17, 2026)
- Установлен Hermes Agent v0.14.0 (NousResearch) из GitHub
- Настроен на OpenRouter с бесплатными моделями
- Добавлен `run_hermes()` в ai-bridge
- Hermes добавлен в PATH через `C:\Users\almax\AppData\Roaming\npm\hermes.cmd`

### Этап 6 — Документация и инструкции (Mai 17, 2026)
- Созданы инструкции для всех 5 агентов в shared папке
- Разграничены роли: оркестраторы (Claude, Qwen Chat) vs субагенты (Gemini, Qwen CLI, Hermes)
- Прописаны fallback-модели и правила обработки ошибок

---

## 9. Преимущества архитектуры

### 9.1 Простота
- **Один файл** (`mcp-server.py`, ~290 строк) — весь функционал
- **Нет баз данных** — только файловая система (shared папка)
- **Нет сетевого сервера** — stdio транспорт, нет портов, нет firewall

### 9.2 Универсальность
- Подключается к **любому MCP-клиенту**: Claude Desktop, Gemini, Qwen, Cline, VS Code
- Легко расширяется: добавить агента = добавить один `@mcp.tool()` метод
- Работает на **Windows** без WSL (все пути нативные)

### 9.3 Надёжность
- Жёстко заданные пути устраняют проблемы PATH в subprocess
- Fallback-цепочки моделей при rate limit
- Graceful degradation: если агент недоступен — работают остальные

### 9.4 Масштабируемость
- **Горизонтально**: добавить нового агента (Claude API, GPT, Ollama) = 1 функция
- **Вертикально**: shared папка масштабируется до любого объёма данных
- Каждый агент может стать оркестратором — динамическое переключение ролей

### 9.5 Бесплатность
- Gemini CLI: бесплатный tier Google AI
- Qwen CLI: бесплатный tier Alibaba DashScope
- Hermes: OpenRouter бесплатные модели (nemotron, gpt-oss, glm, deepseek)

---

## 10. Файловая структура проекта

```
C:\Users\almax\ai-bridge\
├── mcp-server.py               ← основной MCP-сервер (FastMCP)
├── Project.md                  ← этот файл
├── restore_qwen_mcp.py         ← утилита восстановления конфига Qwen
├── shared\                     ← шина данных между агентами
│   ├── AI_BRIDGE_MASTER.md     ← единая мастер-инструкция
│   ├── CLAUDE_DELEGATION_RULES.md
│   ├── QWEN_CHAT_INSTRUCTIONS.md
│   ├── GEMINI_INSTRUCTIONS.md
│   ├── QWEN_CLI_INSTRUCTIONS.md
│   ├── HERMES_INSTRUCTIONS.md
│   ├── claude_inbox.txt        ← async задачи для Claude
│   └── [результаты агентов]
│
C:\Users\almax\hermes-agent\    ← Hermes Agent (NousResearch)
├── .venv\Scripts\hermes.exe    ← исполняемый файл
├── cli-config.yaml             ← модель + провайдер
└── .env                        ← OPENROUTER_API_KEY

C:\Users\almax\.gemini\
└── settings.json               ← модель + MCP конфиг + checkpointing=false

C:\Users\almax\AppData\Roaming\npm\
├── gemini.cmd                  ← Gemini CLI launcher
├── qwen.cmd                    ← Qwen CLI launcher
└── hermes.cmd                  ← Hermes launcher (добавлен)
```

---

## 11. Планы развития

### Краткосрочные
- [ ] `run_claude_api()` — вызов Claude API (Anthropic SDK) как субагента
- [ ] Мониторинг inbox: автоматическая проверка `claude_inbox.txt` по расписанию
- [ ] `get_bridge_status` расширить: проверять все 3 агента ping-ом

### Среднесрочные
- [ ] Логирование всех вызовов в `shared/bridge_log.jsonl`
- [ ] Метрики: время ответа, rate limit события, fallback статистика
- [ ] Web UI для мониторинга shared папки и очереди задач

### Долгосрочные
- [ ] Подключение локальных моделей через Lemonade (NPU, offline)
- [ ] Параллельный запуск задач (asyncio вместо subprocess.run)
- [ ] Персистентная память через flying-rag (векторный поиск по истории задач)
