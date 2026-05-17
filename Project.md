# AI-Bridge MCP — Project Documentation

> Version: 2.0 | Date: 2026-05-17
> Path: `C:\Users\almax\ai-bridge\`

---

## 1. Concept

**AI-Bridge** — FastMCP stdio server enabling 5 AI agents to call each other, share data via a common folder, and build multi-agent pipelines. One Python file (~300 lines), no database, no network server.

```
Любой агент → ai-bridge MCP → Любой другой агент
```

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  ORCHESTRATORS (primary)                    │
│   Claude Desktop              Qwen Chat                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
              ┌────────▼────────┐
              │   AI-BRIDGE MCP │  mcp-server.py (FastMCP)
              │  stdio transport│  Python 3.13
              │  10 tools       │  JSONL logging · asyncio
              └───┬─────┬───┬───┘
                  │     │   │
         ┌────────▼─┐ ┌─▼──────┐ ┌──▼─────┐
         │Gemini CLI│ │Qwen CLI│ │ Hermes │
         │Node.js   │ │Node.js │ │Python  │
         │Google AI │ │Alibaba │ │OpenRtr │
         └──────────┘ └────────┘ └────────┘
```

| Agent | Role | Called via | Can orchestrate |
|-------|------|-----------|----------------|
| Claude Desktop | Orchestrator | — (calls bridge) | ✅ Always |
| Qwen Chat | Orchestrator | — (calls bridge) | ✅ Always |
| Gemini CLI | Subagent | `run_gemini()` | ✅ Optional |
| Qwen CLI | Subagent | `run_qwen()` | ✅ Optional |
| Hermes Agent | Subagent | `run_hermes()` | ✅ Optional |

> ⚠️ **Qwen Chat ≠ Qwen CLI** — Chat is a desktop orchestrator (cannot be called). CLI is a subagent called via `run_qwen()`.

---

## 3. MCP Tools (10)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `get_bridge_status` | — | Parallel live ping all 3 agents via ThreadPoolExecutor |
| `run_gemini` | `prompt`, `use_tools=False` | Gemini CLI · text gen or shell (yolo) |
| `run_qwen` | `prompt` | Qwen Code CLI · writes files by absolute path |
| `run_hermes` | `prompt` | Hermes Agent · shell + memory + skills |
| `run_parallel_agents` | `tasks_json` | asyncio.to_thread concurrent execution |
| `get_bridge_log` | `last_n=20` | JSONL stats: latency / status / tokens saved |
| `save_to_shared` | `filename`, `content` | Write to shared folder |
| `read_from_shared` | `filename` | Read from shared folder |
| `list_shared` | — | List shared folder |
| `task_for_claude` | `task`, `from_agent` | Async queue → `claude_inbox.txt` |

---

## 4. Models & Fallbacks

### Gemini CLI — Google AI (free)
| # | Model |
|---|-------|
| 1 | `gemini-3.1-pro-preview` |
| 2 | `gemini-3-flash-preview` |
| 3 | `gemini-3.1-flash-lite-preview` |

### Qwen CLI — Alibaba DashScope
| # | Model |
|---|-------|
| 1 | `qwen3.6-plus` |
| 2 | `deepseek-v4-pro` |
| 3 | `glm-5.1` |
| 4 | `deepseek-v4-flash` |

### Hermes — OpenRouter (free tier)
| # | Model | Status |
|---|-------|--------|
| 1 | `openai/gpt-oss-120b:free` | ✅ ~47s |
| 2 | `nvidia/nemotron-3-super-120b-a12b:free` | ✅ ~50s |
| 3 | ~~`z-ai/glm-4.5-air:free`~~ | ❌ timeout |
| 4 | ~~`deepseek/deepseek-v4-flash:free`~~ | ❌ timeout |

---

## 5. Delegation Matrix

| Task | Agent | Notes |
|------|-------|-------|
| Code / text generation | Gemini (`use_tools=False`) | Prompt < 150 words |
| Shell / pip / logs | Gemini (`use_tools=True`) | NOT for file writes |
| Write files | Qwen CLI | Use absolute path. Prompt < 100 words |
| Multi-step + memory | Hermes | Prompt < 120 words |
| Parallel tasks | `run_parallel_agents` | asyncio, all agents simultaneously |
| Web search | Gemini or Hermes | Both have web access |
| Fallback | Orchestrator does it | If 3 retries fail |

---

## 6. Error Handling Rules

| Error | Action |
|-------|--------|
| Rate Limit / 429 | Switch model down fallback list → wait 15-30s → retry |
| Timeout | Shorten prompt (< 80 words), split task → retry |
| MCP Connection closed | Wait 10s → retry up to 3 times |
| Empty response | Shorter prompt, switch model |
| **Max 3 attempts** | Then pass to next agent or do it yourself |

---

## 7. Technical Details

### stdio Transport
MCP uses stdin/stdout as protocol pipe. Any `print()` before `mcp.run()` breaks the connection. FastMCP handles this automatically.

### PATH in subprocess
subprocess inherits empty PATH without `node.exe`, `git.exe`. Fix: **hardcoded absolute paths**:
```python
NODE_EXE = r"C:\Program Files\nodejs\node.exe"
GEMINI_BUNDLE = r"C:\Users\...\node_modules\@google\gemini-cli\bundle\gemini.js"
```

### Gemini Timeout Fix (v2.0)
Gemini CLI reads `~/.gemini/settings.json` and launches all 7 MCP servers on startup → subprocess hangs > 120s.
Fix: `GEMINI_CONFIG_DIR` → `gemini-subprocess-config/settings.json` with empty `mcpServers: {}`.
Result: **>120s timeout → ~25s**.

### JSONL Logging (v2.0)
`@_logged` decorator wraps all agent tools:
```python
record = {timestamp, agent, prompt_words, result_words,
          latency_s, status, error_msg, tokens_saved_estimate}
```
Token savings estimate: `result_words × 1.3` (cost of generating locally vs Claude doing it).

### Hermes quiet mode
```
hermes chat -q "prompt" -Q --yolo
# -Q = quiet (final answer only, session_id in stderr)
# Cold start: ~50s Python env loading
```

### Parallel execution (v2.0)
- `get_bridge_status`: ThreadPoolExecutor(3) — all agents pinged simultaneously
- `run_parallel_agents`: asyncio.gather + asyncio.to_thread — non-blocking concurrent calls

---

## 8. Development History

| Stage | Date | Changes |
|-------|------|---------|
| 1 — Base bridge | May 14, 2026 | FastMCP server, run_gemini/qwen, shared folder |
| 2 — Subprocess fixes | May 14 | node.exe absolute path, git checkpointing, Qwen auth |
| 3 — Multi-agent comms | May 14 | task_for_claude, full mesh verification (FIFA WC test) |
| 4 — Cline integration | May 16 | VS Code MCP config, bidirectional Claude↔Cline |
| 5 — Hermes Agent | May 17 | NousResearch Hermes v0.14.0, OpenRouter free models |
| 6 — v2.0 features | May 17 | Parallel ping, JSONL logging, asyncio runner, GitHub |

---

## 9. v2.0 New Features

- **`get_bridge_status`**: parallel ping via ThreadPoolExecutor (56s vs 150s sequential)
- **`run_parallel_agents`**: asyncio concurrent multi-agent execution
- **`get_bridge_log`**: JSONL stats with token savings tracking
- **`@_logged`**: automatic logging decorator on all agent tools
- **Gemini fix**: `GEMINI_CONFIG_DIR` isolates subprocess from 7-server MCP config
- **GitHub**: https://github.com/Kritik35/ai-bridge

---

## 10. File Structure

```
ai-bridge/
├── mcp-server.py                  ← main server (10 tools, ~300 lines)
├── requirements.txt               ← fastmcp, python-dotenv
├── .env                           ← secrets (gitignored)
├── .env.example                   ← template
├── .gitignore
├── README.md
├── Project.md                     ← this file
├── gemini-subprocess-config/
│   └── settings.json              ← minimal Gemini config (no MCP servers)
└── shared/                        ← data bus between agents
    ├── AI_BRIDGE_MASTER.md        ← master instructions
    ├── CLAUDE_DELEGATION_RULES.md
    ├── QWEN_CHAT_INSTRUCTIONS.md
    ├── GEMINI_INSTRUCTIONS.md
    ├── QWEN_CLI_INSTRUCTIONS.md
    ├── HERMES_INSTRUCTIONS.md
    ├── claude_inbox.txt           ← async task queue
    └── bridge_log.jsonl           ← call history + stats
```

---

## 11. Configuration

### .env
```env
DASHSCOPE_API_KEY=your_key   # Qwen CLI
OPENROUTER_API_KEY=your_key  # Hermes Agent
```

### Hermes model change
Edit `C:\Users\almax\hermes-agent\cli-config.yaml`:
```yaml
model:
  default: "openai/gpt-oss-120b:free"
  provider: "openrouter"
```
