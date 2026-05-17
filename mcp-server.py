# -*- coding: utf-8 -*-
# AI-Bridge MCP Server v2.0
# Agents: Gemini CLI · Qwen CLI · Hermes Agent
# New in v2.0: live status ping, JSONL logging, token savings, async parallel tool

from fastmcp import FastMCP
import subprocess
import asyncio
import os
import re
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from functools import wraps

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

mcp = FastMCP("AI Bridge")

# ── Пути ────────────────────────────────────────────────────────────────────
SHARED_DIR   = Path("C:/Users/almax/ai-bridge/shared")
SHARED_DIR.mkdir(exist_ok=True)
LOG_FILE     = SHARED_DIR / "bridge_log.jsonl"

NODE_EXE      = r"C:\Program Files\nodejs\node.exe"
GEMINI_BUNDLE = r"C:\Users\almax\AppData\Roaming\npm\node_modules\@google\gemini-cli\bundle\gemini.js"
GEMINI_CONFIG = str(Path(__file__).parent / "gemini-subprocess-config")   # без MCP-серверов
QWEN_BUNDLE   = r"C:\Users\almax\AppData\Roaming\npm\node_modules\@qwen-code\qwen-code\cli.js"
HERMES_EXE    = r"C:\Users\almax\hermes-agent\.venv\Scripts\hermes.exe"
HERMES_DIR    = r"C:\Users\almax\hermes-agent"

# ── Logging (Qwen authored) ──────────────────────────────────────────────────
def _log_call(agent: str, prompt: str, result: str, latency_s: float, error: str = None):
    """Append one JSON line to bridge_log.jsonl."""
    prompt_words = len(prompt.split())
    result_words = len(result.split()) if result else 0
    record = {
        "timestamp":            datetime.now(timezone.utc).isoformat(),
        "agent":                agent,
        "prompt_words":         prompt_words,
        "result_words":         result_words,
        "latency_s":            round(latency_s, 2),
        "status":               "error" if error else "ok",
        "error_msg":            error,
        "tokens_saved_estimate": round(result_words * 1.3),
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # logging must never break the main flow


def _logged(agent_name: str):
    """Decorator: wrap a tool function with timing + JSONL logging."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.monotonic()
            error = None
            result = ""
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                latency = time.monotonic() - start
                prompt = args[0] if args else kwargs.get("prompt", "")
                _log_call(agent_name, str(prompt), str(result), latency, error)
        return wrapper
    return decorator

# ── Env helpers ──────────────────────────────────────────────────────────────
def _win_path() -> str:
    paths = [r"C:\Windows\System32", r"C:\Windows",
             r"C:\Windows\System32\WindowsPowerShell\v1.0",
             r"C:\Program Files\Git\bin", r"C:\Program Files\Git\cmd",
             r"C:\Program Files\nodejs", r"C:\Users\almax\AppData\Roaming\npm"]
    cur = os.environ.get("PATH", os.environ.get("Path", ""))
    return ";".join(paths) + ";" + cur if r"Windows\System32" not in cur else cur

# ── 1. get_bridge_status — live ping all 3 agents (Gemini authored) ──────────
@mcp.tool()
def get_bridge_status() -> str:
    """Проверяет статус моста: живой ping всех трёх агентов параллельно."""

    def ping(name: str, cmd: list, timeout: int, extra_env: dict) -> str:
        env = os.environ.copy()
        env.update(extra_env)
        t0 = time.monotonic()
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout,
                               stdin=subprocess.DEVNULL, env=env, cwd=str(SHARED_DIR))
            latency = time.monotonic() - t0
            ok = r.returncode == 0 and r.stdout
            status = "OK" if ok else "ERROR"
            return f"  {name}: {status} ({latency:.1f}s)"
        except subprocess.TimeoutExpired:
            return f"  {name}: TIMEOUT (>{timeout}s)"
        except Exception as e:
            return f"  {name}: ERROR ({e})"

    agents = [
        ("Gemini", [NODE_EXE, GEMINI_BUNDLE, "-p", "ping", "--skip-trust",
                    "-m", "gemini-3.1-pro-preview"],
         30, {"GEMINI_CONFIG_DIR": GEMINI_CONFIG, "NO_COLOR": "1",
              "CI": "true", "GEMINI_DISABLE_CHECKPOINTING": "true",
              "PATH": _win_path(), "Path": _win_path()}),
        ("Qwen", [NODE_EXE, QWEN_BUNDLE, "-p", "ping", "--yolo"],
         35, {"DASHSCOPE_API_KEY": os.environ.get("DASHSCOPE_API_KEY", ""),
              "NO_COLOR": "1", "CI": "true",
              "PATH": _win_path(), "Path": _win_path()}),
        ("Hermes", [HERMES_EXE, "chat", "-q", "ping", "-Q", "--yolo"],
         90, {"OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", ""),
              "NO_COLOR": "1", "USERPROFILE": r"C:\Users\almax",
              "HOME": r"C:\Users\almax", "APPDATA": r"C:\Users\almax\AppData\Roaming"}),
    ]

    lines = ["AI-Bridge Status:"]
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(ping, n, cmd, t, env): n for n, cmd, t, env in agents}
        results = {futures[f]: f.result() for f in futures}
    for name, _, _, _ in agents:
        lines.append(results[name])
    lines.append(f"  Shared: {SHARED_DIR}")
    lines.append(f"  Log: {LOG_FILE}")
    return "\n".join(lines)

# ── 2. run_gemini ────────────────────────────────────────────────────────────
@mcp.tool()
@_logged("gemini")
def run_gemini(prompt: str, use_tools: bool = False) -> str:
    """Gemini CLI. use_tools=False: генерация текста. use_tools=True: shell/поиск (yolo)."""
    if not os.path.exists(GEMINI_BUNDLE):
        return f"Error: Gemini bundle not found at {GEMINI_BUNDLE}"

    cmd = [NODE_EXE, GEMINI_BUNDLE, "-p", prompt, "--skip-trust",
           "-m", "gemini-3.1-pro-preview"]
    if use_tools:
        cmd.append("--yolo")

    env = os.environ.copy()
    env.update({"PATH": _win_path(), "Path": _win_path(),
                "CI": "true", "NO_COLOR": "1", "FORCE_COLOR": "0",
                "GEMINI_CLI_TRUST_WORKSPACE": "true",
                "GEMINI_DISABLE_CHECKPOINTING": "true",
                "GEMINI_CLI_NO_CHECKPOINTING": "true",
                "CHECKPOINT_ENABLED": "false",
                "GEMINI_CONFIG_DIR": GEMINI_CONFIG})
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=120,
                           stdin=subprocess.DEVNULL, env=env, cwd=str(SHARED_DIR))
        out = re.sub(r'\x1b\[[0-9;]*[A-Za-zm]', '',
                     r.stdout.decode("utf-8", errors="replace").strip())
        if out:
            return out
        try:
            err = r.stderr.decode("cp1251", errors="replace").strip()
        except Exception:
            err = r.stderr.decode("utf-8", errors="replace").strip()
        err_clean = "\n".join(l for l in err.splitlines()
                              if any(c.isascii() and c.isprintable() for c in l))
        if "429" in err or "capacity" in err:
            return "Error: Gemini rate limit. Switch model."
        return f"Gemini no output. Stderr: {err_clean[:400]}" if err_clean else "Gemini returned empty response."
    except subprocess.TimeoutExpired:
        return "Error: Gemini timeout (>120s)."
    except Exception as e:
        return f"Execution Failed: {e}"

# ── 3. run_qwen ──────────────────────────────────────────────────────────────
@mcp.tool()
@_logged("qwen")
def run_qwen(prompt: str) -> str:
    """Qwen Code CLI. Пишет файлы напрямую по абсолютному пути."""
    if not os.path.exists(QWEN_BUNDLE):
        return f"Error: Qwen bundle not found at {QWEN_BUNDLE}"

    env = os.environ.copy()
    env.update({"CI": "true", "NO_COLOR": "1", "FORCE_COLOR": "0",
                "DASHSCOPE_API_KEY": os.environ.get("DASHSCOPE_API_KEY", "")})
    cur = env.get("PATH", env.get("Path", ""))
    extras = r"C:\Windows\System32;C:\Windows;C:\Program Files\nodejs;C:\Users\almax\AppData\Roaming\npm"
    if r"Windows\System32" not in cur:
        env["PATH"] = extras + ";" + cur
        env["Path"] = env["PATH"]
    try:
        r = subprocess.run([NODE_EXE, QWEN_BUNDLE, "-p", prompt, "--yolo"],
                           capture_output=True, timeout=180,
                           stdin=subprocess.DEVNULL, env=env)
        out = re.sub(r'\x1b\[[0-9;]*[A-Za-zm]', '',
                     r.stdout.decode("utf-8", errors="replace").strip())
        if out:
            return out
        err = r.stderr.decode("utf-8", errors="replace").strip()
        if "auth" in err.lower() or "login" in err.lower():
            return "Error: Qwen requires authentication."
        return f"Qwen CLI Error: {err[:400]}" if err else "Qwen returned empty response."
    except subprocess.TimeoutExpired:
        return "Error: Qwen timeout (>180s)."
    except Exception as e:
        return f"Execution Failed: {e}"

# ── 4. run_hermes ────────────────────────────────────────────────────────────
@mcp.tool()
@_logged("hermes")
def run_hermes(prompt: str) -> str:
    """Hermes Agent (OpenRouter). Многошаговые задачи, memory, shell."""
    if not os.path.exists(HERMES_EXE):
        return f"Error: Hermes not found at {HERMES_EXE}"

    env = os.environ.copy()
    env.update({"OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", ""),
                "NO_COLOR": "1", "FORCE_COLOR": "0",
                "USERPROFILE": r"C:\Users\almax", "HOME": r"C:\Users\almax",
                "APPDATA": r"C:\Users\almax\AppData\Roaming"})
    try:
        r = subprocess.run([HERMES_EXE, "chat", "-q", prompt, "-Q", "--yolo"],
                           capture_output=True, timeout=300,
                           stdin=subprocess.DEVNULL, env=env, cwd=HERMES_DIR)
        out = re.sub(r'\x1b\[[0-9;]*[A-Za-zm]', '',
                     r.stdout.decode("utf-8", errors="replace").strip())
        if out:
            return out
        err = r.stderr.decode("utf-8", errors="replace").strip()
        return f"Hermes stderr: {err[:400]}" if err else "Hermes returned empty response."
    except subprocess.TimeoutExpired:
        return "Error: Hermes timeout (>300s). Cold start ~50s."
    except Exception as e:
        return f"Execution Failed: {e}"

# ── 5. run_parallel_agents — asyncio (Gemini + Hermes authored) ──────────────
@mcp.tool()
async def run_parallel_agents(tasks_json: str) -> str:
    """Запустить несколько агентов параллельно через asyncio.
    tasks_json: JSON-массив задач, например:
    [{"agent":"gemini","prompt":"что такое MCP?"},{"agent":"qwen","prompt":"ping"}]
    Возвращает JSON-массив результатов с полями: agent, result, latency_s, status."""

    _dispatch = {"gemini": run_gemini, "qwen": run_qwen, "hermes": run_hermes}

    async def call_one(task: dict) -> dict:
        agent = task.get("agent", "").lower()
        prompt = task.get("prompt", "")
        fn = _dispatch.get(agent)
        if not fn:
            return {"agent": agent, "result": f"Unknown agent: {agent}",
                    "latency_s": 0.0, "status": "error"}
        t0 = time.monotonic()
        try:
            # run_gemini/run_qwen/run_hermes — синхронные; запускаем в thread
            result = await asyncio.to_thread(fn, prompt)
            latency = round(time.monotonic() - t0, 2)
            status = "error" if result.startswith("Error") else "ok"
            return {"agent": agent, "result": result, "latency_s": latency, "status": status}
        except Exception as e:
            return {"agent": agent, "result": str(e),
                    "latency_s": round(time.monotonic() - t0, 2), "status": "error"}

    try:
        tasks = json.loads(tasks_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}"})

    results = await asyncio.gather(*[call_one(t) for t in tasks])
    return json.dumps(results, ensure_ascii=False, indent=2)

# ── 6. get_bridge_log — статистика логов ────────────────────────────────────
@mcp.tool()
def get_bridge_log(last_n: int = 20) -> str:
    """Показать последние N записей лога + суммарную статистику по агентам."""
    if not LOG_FILE.exists():
        return "Log file not found. No calls logged yet."
    lines = LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return "Log is empty."

    records = []
    for l in lines:
        try:
            records.append(json.loads(l))
        except Exception:
            pass

    # Статистика
    stats: dict = {}
    for r in records:
        a = r.get("agent", "?")
        if a not in stats:
            stats[a] = {"calls": 0, "ok": 0, "errors": 0,
                        "total_latency": 0.0, "tokens_saved": 0}
        stats[a]["calls"] += 1
        stats[a]["ok" if r.get("status") == "ok" else "errors"] += 1
        stats[a]["total_latency"] += r.get("latency_s", 0)
        stats[a]["tokens_saved"] += r.get("tokens_saved_estimate", 0)

    lines_out = [f"=== AI-Bridge Log (total {len(records)} calls) ===\n"]
    lines_out.append("--- Stats per agent ---")
    for agent, s in sorted(stats.items()):
        avg = s["total_latency"] / s["calls"] if s["calls"] else 0
        lines_out.append(
            f"  {agent}: {s['calls']} calls | {s['ok']} ok / {s['errors']} err "
            f"| avg {avg:.1f}s | ~{s['tokens_saved']} tokens saved"
        )

    lines_out.append(f"\n--- Last {last_n} calls ---")
    for r in records[-last_n:]:
        ts = r.get("timestamp", "")[:19].replace("T", " ")
        lines_out.append(
            f"  [{ts}] {r.get('agent','?'):8s} "
            f"{r.get('status','?'):8s} "
            f"{r.get('latency_s',0):5.1f}s "
            f"prompt={r.get('prompt_words',0)}w "
            f"result={r.get('result_words',0)}w "
            f"~{r.get('tokens_saved_estimate',0)}tok"
        )
    return "\n".join(lines_out)

# ── 7. Shared file tools ─────────────────────────────────────────────────────
@mcp.tool()
def save_to_shared(filename: str, content: str) -> str:
    """Сохранить текст в файл для обмена с другими агентами."""
    try:
        (SHARED_DIR / filename).write_text(content, encoding="utf-8")
        return f"Saved to {SHARED_DIR / filename}"
    except Exception as e:
        return f"Save Error: {e}"

@mcp.tool()
def read_from_shared(filename: str) -> str:
    """Прочитать файл из shared папки."""
    fp = SHARED_DIR / filename
    if fp.exists():
        try:
            return fp.read_text(encoding="utf-8")
        except Exception as e:
            return f"Read Error: {e}"
    return f"File {filename} not found."

@mcp.tool()
def list_shared() -> str:
    """Список файлов в shared папке."""
    try:
        files = sorted(SHARED_DIR.iterdir())
        if not files:
            return "Shared folder is empty."
        return "Files:\n" + "\n".join(f"  {f.name} ({f.stat().st_size}b)" for f in files)
    except Exception as e:
        return f"List Error: {e}"

@mcp.tool()
def task_for_claude(task: str, from_agent: str = "unknown") -> str:
    """Асинхронная очередь задач для Claude через claude_inbox.txt."""
    try:
        inbox = SHARED_DIR / "claude_inbox.txt"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(inbox, "a", encoding="utf-8") as f:
            f.write(f"\n[{ts}] FROM: {from_agent}\n{task}\n---\n")
        return f"Task queued for Claude. File: {inbox}"
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    mcp.run()
