# 🌉 AI-Bridge MCP

> Единый мост для многоагентной AI-системы на базе Model Context Protocol (MCP)

**AI-Bridge** — MCP-сервер на FastMCP, который позволяет пяти AI-агентам вызывать друг друга, обмениваться данными и строить многоагентные пайплайны. Один Python-файл (~300 строк) без баз данных и сетевых серверов.

---

## Архитектура

```
┌─────────────────────────────────────────────┐
│         ОРКЕСТРАТОРЫ (первичные)            │
│   Claude Desktop        Qwen Chat           │
└────────────────┬────────────────────────────┘
                 │ run_gemini / run_qwen / run_hermes
        ┌────────▼────────┐
        │  AI-BRIDGE MCP  │  ← mcp-server.py (FastMCP)
        │  stdio transport│  ← 8 инструментов
        └──┬──────┬────┬──┘
           ▼      ▼    ▼
      Gemini   Qwen   Hermes
       CLI      CLI   Agent
    (субагенты-исполнители)
```

| Агент | Роль | Вызов |
|-------|------|-------|
| Claude Desktop | Оркестратор | сам вызывает bridge |
| Qwen Chat | Оркестратор | сам вызывает bridge |
| Gemini CLI | Субагент | `run_gemini()` |
| Qwen CLI | Субагент | `run_qwen()` |
| Hermes Agent | Субагент | `run_hermes()` |

> Каждый агент может опционально стать оркестратором — делегировать задачи другим.

---

## Инструменты (8 штук)

| Инструмент | Параметры | Назначение |
|------------|-----------|-----------|
| `get_bridge_status` | — | Проверка работоспособности |
| `run_gemini` | `prompt`, `use_tools=False` | Вызов Google Gemini CLI |
| `run_qwen` | `prompt` | Вызов Qwen Code CLI |
| `run_hermes` | `prompt` | Вызов Hermes Agent |
| `save_to_shared` | `filename`, `content` | Запись в shared папку |
| `read_from_shared` | `filename` | Чтение из shared папки |
| `list_shared` | — | Список файлов shared |
| `task_for_claude` | `task`, `from_agent` | Асинхронная задача для Claude |

### Матрица делегирования

| Задача | Агент |
|--------|-------|
| Генерация кода / текста | `run_gemini(use_tools=False)` |
| Shell / pip / установка | `run_gemini(use_tools=True)` |
| Запись файлов | `run_qwen()` — с абсолютным путём |
| Многошаговые + memory | `run_hermes()` |
| Поиск в интернете | Gemini или Hermes |

---

## Установка

### Требования
- Python 3.11+
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) (`npm install -g @google/gemini-cli`)
- [Qwen Code CLI](https://github.com/QwenLM/qwen-code) (`npm install -g @qwen-code/qwen-code`)
- [Hermes Agent](https://github.com/NousResearch/hermes-agent) (опционально)

### Быстрый старт

```bash
git clone https://github.com/YOUR_USERNAME/ai-bridge.git
cd ai-bridge
pip install -r requirements.txt
```

Скопируйте `.env.example` в `.env` и заполните ключи:
```bash
cp .env.example .env
```

```env
DASHSCOPE_API_KEY=your_dashscope_key   # Qwen CLI
OPENROUTER_API_KEY=your_openrouter_key # Hermes Agent
```

### Настройте пути в `mcp-server.py`

Найдите блок с константами и укажите пути к вашим CLI-инструментам:

```python
# Путь к node.exe
NODE_EXE = r"C:\Program Files\nodejs\node.exe"

# Пути к Gemini CLI
GEMINI_BUNDLE = r"C:\Users\USERNAME\AppData\Roaming\npm\node_modules\@google\gemini-cli\bundle\gemini.js"

# Пути к Qwen CLI
QWEN_BUNDLE = r"C:\Users\USERNAME\AppData\Roaming\npm\node_modules\@qwen-code\qwen-code\cli.js"

# Путь к Hermes
HERMES_EXE = r"C:\Users\USERNAME\hermes-agent\.venv\Scripts\hermes.exe"
```

---

## Подключение к клиентам

### Claude Desktop
Добавьте в `%APPDATA%\Claude\claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "ai-bridge": {
      "command": "python",
      "args": ["C:\\path\\to\\ai-bridge\\mcp-server.py"]
    }
  }
}
```

### Gemini CLI
Добавьте в `~/.gemini/settings.json`:
```json
{
  "mcpServers": {
    "ai-bridge": {
      "command": "python",
      "args": ["C:\\path\\to\\ai-bridge\\mcp-server.py"]
    }
  },
  "general": { "checkpointing": { "enabled": false } }
}
```

### Qwen Chat (Desktop)
В настройках MCP добавьте сервер `ai-bridge` с командой `python` и путём к `mcp-server.py`.

### Cline (VS Code)
Добавьте в `cline_mcp_settings.json`:
```json
{
  "mcpServers": {
    "ai-bridge": {
      "command": "python",
      "args": ["C:\\path\\to\\ai-bridge\\mcp-server.py"]
    }
  }
}
```

---

## Shared папка

Файловая шина для обмена данными между агентами:

```
shared/
├── AI_BRIDGE_MASTER.md        ← единая инструкция для всех агентов
├── CLAUDE_DELEGATION_RULES.md ← правила для Claude Desktop
├── QWEN_CHAT_INSTRUCTIONS.md  ← правила для Qwen Chat
├── GEMINI_INSTRUCTIONS.md     ← правила для Gemini CLI
├── QWEN_CLI_INSTRUCTIONS.md   ← правила для Qwen CLI
├── HERMES_INSTRUCTIONS.md     ← правила для Hermes
└── claude_inbox.txt           ← асинхронная очередь задач для Claude
```

---

## Технические детали

**Транспорт: stdio** — MCP использует stdin/stdout как протокол. Любой `print()` до `mcp.run()` ломает соединение.

**PATH в subprocess** — при запуске через MCP subprocess наследует пустой PATH. Решение: абсолютные пути к `node.exe` и CLI-бандлам.

**Gemini Checkpointing** — Gemini CLI по умолчанию пытается использовать git. Отключается через `GEMINI_DISABLE_CHECKPOINTING=true` и `cwd` без `.git`.

**Hermes cold start** — ~50 сек на запуск Python-окружения. Timeout в `run_hermes()` установлен в 300 сек.

---

## Провайдеры и модели

### Gemini CLI — Google AI (бесплатно)
`gemini-3.1-pro-preview` → `gemini-3-flash-preview` → `gemini-3.1-flash-lite-preview`

### Qwen CLI — Alibaba DashScope
`qwen3.6-plus` → `deepseek-v4-pro` → `glm-5.1` → `deepseek-v4-flash`

### Hermes — OpenRouter (free tier)
`openai/gpt-oss-120b:free` → `nvidia/nemotron-3-super-120b-a12b:free`

---

## Структура проекта

```
ai-bridge/
├── mcp-server.py       ← основной MCP-сервер
├── requirements.txt    ← зависимости Python
├── .env.example        ← шаблон переменных окружения
├── Project.md          ← полная проектная документация
├── README.md           ← этот файл
└── shared/             ← инструкции и шина данных
    └── *.md
```

---

## Лицензия

MIT

---

*Создано в рамках разработки локального RAG-ассистента для BIM-отдела*
