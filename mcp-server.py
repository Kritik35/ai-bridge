# -*- coding: utf-8 -*-
from fastmcp import FastMCP
import subprocess
import os
import re
from pathlib import Path

# Load .env if present (python-dotenv optional)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass
# Инициализация MCP сервера
mcp = FastMCP("AI Bridge")

# Папка для обмена данными
SHARED_DIR = Path("C:/Users/almax/ai-bridge/shared")
SHARED_DIR.mkdir(exist_ok=True)

# Пути к Gemini
GEMINI_BUNDLE = r"C:\Users\almax\AppData\Roaming\npm\node_modules\@google\gemini-cli\bundle\gemini.js"
GEMINI_PS1    = r"C:\Users\almax\AppData\Roaming\npm\gemini.ps1"

# Полный путь к node.exe — чтобы не зависеть от PATH в окружении Qwen
NODE_EXE = r"C:\Program Files\nodejs\node.exe"

# Пути к Qwen CLI (Node.js bundle)
QWEN_BUNDLE = r"C:\Users\almax\AppData\Roaming\npm\node_modules\@qwen-code\qwen-code\cli.js"
QWEN_CMD = r"C:\Users\almax\AppData\Roaming\npm\qwen.cmd"
QWEN_PS1 = r"C:\Users\almax\AppData\Roaming\npm\qwen.ps1"

# Путь к Hermes Agent
HERMES_EXE = r"C:\Users\almax\hermes-agent\.venv\Scripts\hermes.exe"
HERMES_DIR = r"C:\Users\almax\hermes-agent"

@mcp.tool()
def get_bridge_status() -> str:
    """Проверяет статус моста и доступность файлов"""
    gemini_exists = os.path.exists(GEMINI_BUNDLE) or os.path.exists(GEMINI_PS1)
    qwen_exists = os.path.exists(QWEN_CMD) or os.path.exists(QWEN_PS1)
    return f"Bridge Status: ONLINE.\nGemini Found: {gemini_exists}\nQwen Found: {qwen_exists}\nShared Folder: {SHARED_DIR}"

@mcp.tool()
def run_gemini(prompt: str, use_tools: bool = False) -> str:
    """Отправить запрос в Gemini CLI.
    use_tools=False (default): только текстовая генерация, без shell-инструментов — быстро и стабильно.
    use_tools=True: с shell/поиском (YOLO mode) — для задач где нужен интернет/файлы."""
    if not os.path.exists(GEMINI_BUNDLE):
        return f"Error: Gemini bundle not found at {GEMINI_BUNDLE}"

    # Базовая команда — полный путь к node.exe, без зависимости от PATH
    # --allowed-mcp-server-names "": не запускать MCP серверы из settings.json
    # (они зависают в subprocess-режиме и замедляют старт)
    # Модель берём из settings.json но передаём явно через флаг для надёжности
    import json as _json
    _settings_path = Path(r"C:\Users\almax\.gemini\settings.json")
    _model = "gemini-3-flash-preview"  # fallback
    try:
        _cfg = _json.loads(_settings_path.read_text(encoding="utf-8"))
        _model = _cfg.get("model", {}).get("name", _model)
    except Exception:
        pass

    if use_tools:
        cmd = [NODE_EXE, GEMINI_BUNDLE, "-p", prompt, "--skip-trust", "--yolo", "-m", _model]
    else:
        cmd = [NODE_EXE, GEMINI_BUNDLE, "-p", prompt, "--skip-trust", "-m", _model]

    # PATH: добавляем Windows системные пути + Git (нужен для checkpointing если включён)
    windows_system_paths = ";".join([
        r"C:\Windows\System32",
        r"C:\Windows",
        r"C:\Windows\System32\WindowsPowerShell\v1.0",
        r"C:\Program Files\Git\bin",
        r"C:\Program Files\Git\cmd",
        r"C:\Program Files\nodejs",
        r"C:\Users\almax\AppData\Roaming\npm",
    ])
    current_path = os.environ.get("PATH", os.environ.get("Path", ""))
    if r"Windows\System32" not in current_path:
        current_path = windows_system_paths + ";" + current_path
    else:
        # Добавляем Git если его нет
        if r"Git\bin" not in current_path and r"Git\cmd" not in current_path:
            current_path = r"C:\Program Files\Git\bin;" + r"C:\Program Files\Git\cmd;" + current_path

    env = os.environ.copy()
    env["PATH"] = current_path
    env["Path"] = current_path
    env["CI"] = "true"
    env["NO_COLOR"] = "1"
    env["FORCE_COLOR"] = "0"
    env["GEMINI_CLI_TRUST_WORKSPACE"] = "true"
    env["GEMINI_DISABLE_CHECKPOINTING"] = "true"   # нет Git в subprocess
    env["GEMINI_CLI_NO_CHECKPOINTING"] = "true"    # альтернативное имя
    env["CHECKPOINT_ENABLED"] = "false"
    # Не ставим TERM=dumb — это вызывает "basic terminal" предупреждения

    # cwd = shared folder (не git-репозиторий, нет .git)
    cwd = str(SHARED_DIR)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=120,
            stdin=subprocess.DEVNULL,
            env=env,
            cwd=cwd
        )

        # Gemini выдаёт UTF-8; убираем ANSI-коды
        output = result.stdout.decode("utf-8", errors="replace").strip()
        output = re.sub(r'\x1b\[[0-9;]*[A-Za-zm]', '', output)

        if output:
            return output

        # stdout пустой — анализируем stderr
        # stderr может быть в cp1251 на Windows, пробуем оба варианта
        try:
            stderr = result.stderr.decode("cp1251", errors="replace").strip()
        except Exception:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()

        # Убираем garbled bytes и оставляем читаемые строки
        stderr_clean = "\n".join(
            line for line in stderr.splitlines()
            if any(c.isascii() and c.isprintable() for c in line)
        )

        if "429" in stderr or "capacity" in stderr:
            return "Error: Gemini rate limit. Try again later."
        if stderr_clean:
            return f"Gemini no output. Stderr: {stderr_clean[:400]}"

        return "Gemini returned empty response."

    except subprocess.TimeoutExpired:
        return "Error: Gemini timeout (>120s)."
    except FileNotFoundError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Execution Failed: {str(e)}"

@mcp.tool()
def run_qwen(prompt: str) -> str:
    """Отправить запрос в Qwen Code CLI"""
    if not os.path.exists(QWEN_BUNDLE):
        return f"Error: Qwen bundle not found at {QWEN_BUNDLE}"
    if not os.path.exists(NODE_EXE):
        return f"Error: node.exe not found at {NODE_EXE}"

    # Вызываем напрямую через node.exe (полный путь) — не зависим от PATH
    cmd = [NODE_EXE, QWEN_BUNDLE, "-p", prompt, "--yolo"]

    env = os.environ.copy()
    env["CI"] = "true"
    env["NO_COLOR"] = "1"
    env["FORCE_COLOR"] = "0"
    # DASHSCOPE_API_KEY из .qwen/settings.json — нужен для аутентификации Qwen CLI
    env.setdefault("DASHSCOPE_API_KEY", os.environ.get("DASHSCOPE_API_KEY", ""))
    # Добавляем Git + системные пути (Qwen CLI тоже может нуждаться)
    cur_path = env.get("PATH", env.get("Path", ""))
    extras = r"C:\Windows\System32;C:\Windows;C:\Program Files\nodejs;C:\Users\almax\AppData\Roaming\npm"
    if r"Windows\System32" not in cur_path:
        env["PATH"] = extras + ";" + cur_path
        env["Path"] = env["PATH"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=180,
            stdin=subprocess.DEVNULL,
            env=env
        )

        output = result.stdout.decode("utf-8", errors="replace").strip()
        output = re.sub(r'\x1b\[[0-9;]*[A-Za-zm]', '', output)

        if output:
            return output

        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        if "auth" in stderr.lower() or "login" in stderr.lower():
            return "Error: Qwen requires authentication. Run 'qwen login' in terminal."
        if stderr:
            return f"Qwen CLI Error: {stderr[:400]}"

        return "Qwen returned empty response."

    except subprocess.TimeoutExpired:
        return "Error: Qwen timeout (>180s)."
    except FileNotFoundError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Execution Failed: {str(e)}"

@mcp.tool()
def run_hermes(prompt: str) -> str:
    """Отправить запрос в Hermes Agent (OpenRouter / nemotron).
    Hermes имеет доступ к shell, файлам, памяти и skills."""
    if not os.path.exists(HERMES_EXE):
        return f"Error: Hermes executable not found at {HERMES_EXE}"

    cmd = [HERMES_EXE, "chat", "-q", prompt, "-Q", "--yolo"]

    env = os.environ.copy()
    env["OPENROUTER_API_KEY"] = os.environ.get("OPENROUTER_API_KEY", "")
    env["NO_COLOR"] = "1"
    env["FORCE_COLOR"] = "0"
    env["USERPROFILE"] = r"C:\Users\almax"
    env["HOME"] = r"C:\Users\almax"
    env["APPDATA"] = r"C:\Users\almax\AppData\Roaming"

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=300,  # Hermes стартует ~50s + генерация; запас 5 мин
            stdin=subprocess.DEVNULL,
            env=env,
            cwd=HERMES_DIR,
        )

        output = result.stdout.decode("utf-8", errors="replace").strip()
        output = re.sub(r'\x1b\[[0-9;]*[A-Za-zm]', '', output)

        if output:
            return output

        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        if stderr:
            return f"Hermes stderr: {stderr[:400]}"
        return "Hermes returned empty response."

    except subprocess.TimeoutExpired:
        return "Error: Hermes timeout (>300s). Hermes startup takes ~50s — try a shorter prompt or switch model in cli-config.yaml."
    except FileNotFoundError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Execution Failed: {str(e)}"

@mcp.tool()
def save_to_shared(filename: str, content: str) -> str:
    """Сохранить текст в файл для обмена с другими ИИ"""
    try:
        filepath = SHARED_DIR / filename
        filepath.write_text(content, encoding='utf-8')
        return f"Saved successfully to {filepath}"
    except Exception as e:
        return f"Save Error: {str(e)}"

@mcp.tool()
def read_from_shared(filename: str) -> str:
    """Прочитать текст из общей папки"""
    filepath = SHARED_DIR / filename
    if filepath.exists():
        try:
            return filepath.read_text(encoding='utf-8')
        except Exception as e:
            return f"Read Error: {str(e)}"
    return f"File {filename} not found in shared folder."

@mcp.tool()
def list_shared() -> str:
    """Показать все файлы в общей папке (для координации между агентами)"""
    try:
        files = list(SHARED_DIR.iterdir())
        if not files:
            return "Shared folder is empty."
        result = []
        for f in sorted(files):
            size = f.stat().st_size
            result.append(f"{f.name} ({size} bytes)")
        return "Files in shared folder:\n" + "\n".join(result)
    except Exception as e:
        return f"List Error: {str(e)}"

@mcp.tool()
def task_for_claude(task: str, from_agent: str = "unknown") -> str:
    """Отправить задачу Клоду (Claude). Задача сохраняется в shared/claude_inbox.txt.
    Claude периодически проверяет этот файл.
    from_agent: имя агента-отправителя (gemini/qwen/qwen_chat/etc)"""
    import datetime
    try:
        inbox = SHARED_DIR / "claude_inbox.txt"
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n[{timestamp}] FROM: {from_agent}\n{task}\n---\n"
        # Append to inbox
        with open(inbox, "a", encoding="utf-8") as f:
            f.write(entry)
        return f"Task saved to Claude inbox. Claude will process it when available.\nFile: {inbox}"
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == "__main__":
    mcp.run()
