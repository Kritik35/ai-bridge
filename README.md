# 🌉 AI-Bridge MCP v2.0

Multi-agent bridge via Model Context Protocol. One Python file connects Claude Desktop, Qwen Chat, Gemini CLI, Qwen CLI and Hermes into a coordinated AI system.

## Architecture

```
┌─────────────────────────────────────────────┐
│    ORCHESTRATORS                            │
│    Claude Desktop        Qwen Chat          │
└──────────────┬──────────────────────────────┘
               │ 10 MCP tools
      ┌────────▼────────┐
      │  AI-BRIDGE MCP  │  mcp-server.py · FastMCP · stdio
      │  JSONL logging  │  parallel ping · asyncio runner
      └──┬──────┬────┬──┘
         ▼      ▼    ▼
    Gemini   Qwen   Hermes
     CLI      CLI   Agent
   (subagents / optional orchestrators)
```

| Agent | Role | Avg latency |
|-------|------|-------------|
| Claude Desktop | Primary orchestrator | — |
| Qwen Chat | Primary orchestrator | — |
| Gemini CLI | Subagent | ~25s |
| Qwen CLI | Subagent | ~30s |
| Hermes Agent | Subagent | ~47s |

## 10 MCP Tools

| Tool | Description |
|------|-------------|
| `get_bridge_status` | Parallel live ping all 3 agents (ThreadPoolExecutor) |
| `run_gemini` | Gemini CLI · `use_tools=False/True` · timeout 120s |
| `run_qwen` | Qwen Code CLI · writes files by absolute path · timeout 180s |
| `run_hermes` | Hermes Agent · shell + memory + skills · timeout 300s |
| `run_parallel_agents` | Run multiple agents concurrently via `asyncio.to_thread` |
| `get_bridge_log` | JSONL stats: calls / errors / avg latency / tokens saved |
| `save_to_shared` | Write file to shared folder |
| `read_from_shared` | Read file from shared folder |
| `list_shared` | List shared folder contents |
| `task_for_claude` | Async task queue → `claude_inbox.txt` |

## Delegation Matrix

| Task | Agent |
|------|-------|
| Code / text generation | `run_gemini(use_tools=False)` |
| Shell / pip / logs | `run_gemini(use_tools=True)` |
| Write files | `run_qwen()` with absolute path |
| Multi-step + memory | `run_hermes()` |
| Parallel tasks | `run_parallel_agents()` |

## Install

```bash
git clone https://github.com/Kritik35/ai-bridge.git
cd ai-bridge
pip install -r requirements.txt
cp .env.example .env
# Fill DASHSCOPE_API_KEY and OPENROUTER_API_KEY in .env
```

Set absolute paths in `mcp-server.py` for your machine (`NODE_EXE`, `GEMINI_BUNDLE`, `QWEN_BUNDLE`, `HERMES_EXE`).

## Client Configs

**Claude Desktop** — `%APPDATA%\Claude\claude_desktop_config.json`
```json
{
  "mcpServers": {
    "ai-bridge": {"command": "python", "args": ["C:\\path\\to\\ai-bridge\\mcp-server.py"]}
  }
}
```

**Gemini CLI** — `~/.gemini/settings.json`
```json
{
  "mcpServers": {
    "ai-bridge": {"command": "python", "args": ["C:\\path\\to\\ai-bridge\\mcp-server.py"]}
  },
  "general": {"checkpointing": {"enabled": false}}
}
```

**Cline (VS Code)** — `cline_mcp_settings.json`
```json
{
  "mcpServers": {
    "ai-bridge": {"command": "python", "args": ["C:\\path\\to\\ai-bridge\\mcp-server.py"]}
  }
}
```

## Models & Fallbacks

**Gemini CLI** (Google AI, free):
`gemini-3.1-pro-preview` → `gemini-3-flash-preview` → `gemini-3.1-flash-lite-preview`

**Qwen CLI** (Alibaba DashScope):
`qwen3.6-plus` → `deepseek-v4-pro` → `glm-5.1` → `deepseek-v4-flash`

**Hermes** (OpenRouter free tier):
`openai/gpt-oss-120b:free` → `nvidia/nemotron-3-super-120b-a12b:free`

## Key Technical Details

| Issue | Fix |
|-------|-----|
| Gemini loads 7 MCP servers on start → timeout | `GEMINI_CONFIG_DIR` → minimal config with empty `mcpServers` |
| subprocess has empty PATH | Hardcoded absolute paths to `node.exe` and CLI bundles |
| Hermes cold start ~50s | `chat -q "prompt" -Q --yolo` · timeout 300s |
| Windows encoding issues | UTF-8 + cp1251 fallback · ANSI codes stripped |
| Agents block each other | `ThreadPoolExecutor` for status · `asyncio.to_thread` for parallel |

## What's New in v2.0

- **`get_bridge_status`**: live parallel ping (ThreadPoolExecutor) instead of file checks
- **`run_parallel_agents`**: asyncio concurrent multi-agent execution
- **`get_bridge_log`**: per-agent stats + token savings estimate
- **`@_logged` decorator**: automatic JSONL logging on all agent tools
- **Gemini timeout fix**: >120s → ~25s via `GEMINI_CONFIG_DIR`

## License

MIT — [github.com/Kritik35/ai-bridge](https://github.com/Kritik35/ai-bridge)
