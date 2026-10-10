#!/usr/bin/env python3
"""極簡 agent harness：給本地 Qwen3.6（llama-server，OpenAI Chat Completions）用的基線。

用法：python3 harness/ [--thinking on|off] [--preserve-thinking] [--base-url URL] [--model ID] [--ctx N] PROMPT
在目前目錄解題，事件以 Pi 的 JSON 格式逐行寫到 stdout（compare-runs.py、watch-agent.py 直接看得懂）。
API key 從環境變數 HARNESS_API_KEY 讀，不放在命令列上。

設計依據見 research_notes/harness-design/四家 harness 設計拆解.md 的「極簡 harness：基線」。
這裡只放基線；要做消融的元件（時間感知、寫入後檢查、禁止整檔覆寫…）之後各自加開關。
只用標準函式庫，不需要 venv。
"""

import argparse
import json
import os
import platform
import signal
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from datetime import date

# 取樣參數照 configs/pi/models.json（Qwen 官方建議值）：思考開與關各一組
SAMPLING = {"on": {"temperature": 1.0, "top_p": 0.95, "top_k": 20},
            "off": {"temperature": 0.7, "top_p": 0.8, "top_k": 20}}
MAX_TOKENS = 65536
MAX_STEPS = 300         # 請求次數上限，防止失控
REPEAT_LIMIT = 5        # 同一個工具呼叫（名稱和參數都相同）連續第 5 次就不執行
OUT_LINES, OUT_BYTES = 2000, 50_000   # 工具輸出超過任一門檻就截斷，全文存檔
LINE_CHARS = 2000       # read 的單行上限
BASH_TIMEOUT, BASH_TIMEOUT_MAX = 120, 600

SYSTEM = """You are a coding assistant. You help the user with software tasks by reading files, running commands, editing code, and writing new files.

Working directory: {cwd}
Platform: {platform}
Date: {today}

Tools:
- read: read a file, or list a directory
- bash: run shell commands (search with rg/grep/find, run programs and tests)
- edit: replace an exact snippet in an existing file
- write: create a new file, or overwrite a whole file

Use paths relative to the working directory. Use edit to change existing files; use write only for new files or complete rewrites."""

TOOLS = [
    {"name": "read",
     "description": "Read a text file. Returns up to 2000 lines starting at `offset`. If `path` is a directory, lists its entries (directories end with /).",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string", "description": "File or directory path"},
         "offset": {"type": "integer", "description": "1-based line number to start from (default 1)"},
         "limit": {"type": "integer", "description": "Maximum number of lines to return (default 2000)"}},
         "required": ["path"]}},
    {"name": "bash",
     "description": "Run a bash command in the working directory and return its combined stdout and stderr. Long output keeps the last 2000 lines; the full output is saved to a file whose path is given.",
     "parameters": {"type": "object", "properties": {
         "command": {"type": "string", "description": "The command to run"},
         "timeout": {"type": "integer", "description": f"Timeout in seconds (default {BASH_TIMEOUT}, max {BASH_TIMEOUT_MAX})"}},
         "required": ["command"]}},
    {"name": "edit",
     "description": "Replace `old_string` with `new_string` in a file. `old_string` must match exactly one place in the file (include enough surrounding lines to make it unique), unless `replace_all` is true.",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string", "description": "File path"},
         "old_string": {"type": "string", "description": "Exact text to replace"},
         "new_string": {"type": "string", "description": "Replacement text"},
         "replace_all": {"type": "boolean", "description": "Replace every occurrence (default false)"}},
         "required": ["path", "old_string", "new_string"]}},
    {"name": "write",
     "description": "Write `content` to a file, creating parent directories as needed. Overwrites the file if it exists.",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string", "description": "File path"},
         "content": {"type": "string", "description": "Full file content"}},
         "required": ["path", "content"]}},
]
TOOL_NAMES = [t["name"] for t in TOOLS]


def emit(event):
    """一行一個事件，馬上 flush：被 timeout 結束時，已經發生的事都留在紀錄裡。"""
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
    sys.stdout.flush()


# ---------- 工具 ----------

class ToolError(Exception):
    """回給模型的錯誤訊息（isError=true），不中斷迴圈。"""


spill_dir = None   # 截斷時存全文的目錄，第一次用到才建


def spill(text, name):
    global spill_dir
    spill_dir = spill_dir or tempfile.mkdtemp(prefix="harness-output.")
    path = os.path.join(spill_dir, f"{name}-{uuid.uuid4().hex[:8]}.txt")
    with open(path, "w") as f:
        f.write(text)
    return path


def tail_truncate(text, name):
    """bash 輸出取尾端（錯誤訊息通常在最後），超過門檻時全文存檔並標出原始大小。"""
    lines = text.split("\n")
    if len(lines) <= OUT_LINES and len(text.encode()) <= OUT_BYTES:
        return text
    kept = lines[-OUT_LINES:]
    while kept and len("\n".join(kept).encode()) > OUT_BYTES:
        kept = kept[len(kept) // 10 + 1:]
    path = spill(text, name)
    return (f"[output truncated: {len(lines)} lines, {len(text.encode())} bytes total; showing the last {len(kept)} lines. "
            f"Full output: {path}]\n" + "\n".join(kept))


def resolve(path):
    return os.path.normpath(os.path.join(os.getcwd(), os.path.expanduser(path)))


def tool_read(path, offset=1, limit=OUT_LINES):
    p = resolve(path)
    if os.path.isdir(p):
        # 目錄也回內容：Qwen Code 的 glob 只回檔案，模型因此把只有子目錄的目錄判成空的
        entries = sorted(e.name + ("/" if e.is_dir() else "") for e in os.scandir(p))
        if not entries:
            return f"{path} is an empty directory"
        shown = entries[:500]
        more = f"\n[{len(entries) - 500} more entries not shown]" if len(entries) > 500 else ""
        return "\n".join(shown) + more
    if not os.path.exists(p):
        raise ToolError(f"File not found: {path}")
    data = open(p, "rb").read()
    if b"\0" in data[:8192]:
        raise ToolError(f"{path} is a binary file ({len(data)} bytes)")
    lines = data.decode(errors="replace").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    offset, limit = max(1, int(offset or 1)), max(1, min(int(limit or OUT_LINES), OUT_LINES))
    if offset > len(lines) and lines:
        raise ToolError(f"offset {offset} is past the end of {path} ({len(lines)} lines)")
    chunk, size, out = lines[offset - 1:offset - 1 + limit], 0, []
    for line in chunk:
        if len(line) > LINE_CHARS:
            line = line[:LINE_CHARS] + f" [line truncated, {len(line)} chars]"
        size += len(line.encode()) + 1
        if size > OUT_BYTES:
            break
        out.append(line)
    end = offset - 1 + len(out)
    text = "\n".join(out)
    if end < len(lines):
        text += f"\n[showing lines {offset}-{end} of {len(lines)}; use offset={end + 1} to continue]"
    return text


running = None   # 執行中的 bash 程序，收到 SIGTERM 時一起收掉


def tool_bash(command, timeout=BASH_TIMEOUT):
    global running
    timeout = max(1, min(int(timeout or BASH_TIMEOUT), BASH_TIMEOUT_MAX))
    # 自己一個程序群組：逾時可以連同它的子程序一起結束
    running = subprocess.Popen(["bash", "-c", command], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, start_new_session=True)
    try:
        out, _ = running.communicate(timeout=timeout)
        code, note = running.returncode, ""
    except subprocess.TimeoutExpired:
        os.killpg(running.pid, signal.SIGKILL)
        out, _ = running.communicate()
        code, note = None, f"[timed out after {timeout}s; the command was killed]"
    finally:
        running = None
    text = tail_truncate(out.decode(errors="replace").rstrip("\n"), "bash")
    if note:
        text += ("\n" if text else "") + note
    elif code:
        text += ("\n" if text else "") + f"[exit code {code}]"
    return text or "[no output]", bool(note or code)


# 寬鬆比對：精確比對失敗時，逐行做越來越寬的正規化再比（Pi、Qwen Code、Codex 都有類似的層次）
_PUNCT = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "‐": "-", "‑": "-",
                        "‒": "-", "–": "-", "—": "-", "−": "-", " ": " ", "　": " "})
LAYERS = [("trailing whitespace", lambda s: s.rstrip()),
          ("leading/trailing whitespace", lambda s: s.strip()),
          ("unicode punctuation", lambda s: unicodedata.normalize("NFKC", s).translate(_PUNCT).strip())]


def fuzzy_spans(content_lines, old_lines, norm):
    target = [norm(s) for s in old_lines]
    normed = [norm(s) for s in content_lines]
    n = len(target)
    return [i for i in range(len(normed) - n + 1) if normed[i:i + n] == target]


def tool_edit(path, old_string, new_string, replace_all=False):
    p = resolve(path)
    if not os.path.isfile(p):
        raise ToolError(f"File not found: {path}")
    if old_string == "":
        raise ToolError("old_string is empty. Use write to create a file.")
    if old_string == new_string:
        raise ToolError("old_string and new_string are identical; nothing to change.")
    content = open(p, encoding="utf-8", errors="replace").read()
    count = content.count(old_string)
    how = ""
    if count:
        if count > 1 and not replace_all:
            raise ToolError(f"Found {count} occurrences of old_string in {path}. Include more surrounding lines to make it unique, or set replace_all.")
        new = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
    else:
        # 以整行為單位比對；old_string 結尾的換行不算一行
        lines = content.split("\n")
        old_lines = old_string.split("\n")
        new_lines = new_string.split("\n")
        if old_lines[-1] == "":
            old_lines.pop()
            if new_lines[-1] == "":
                new_lines.pop()
        for name, norm in LAYERS:
            spans = fuzzy_spans(lines, old_lines, norm)
            if spans:
                break
        else:
            raise ToolError(f"old_string was not found in {path}. It must match the file exactly, including indentation. Read the file again to get the current text.")
        if len(spans) > 1 and not replace_all:
            raise ToolError(f"Found {len(spans)} occurrences of old_string in {path} (ignoring {name}). Include more surrounding lines to make it unique, or set replace_all.")
        n = len(old_lines)
        for i in reversed(spans if replace_all else spans[:1]):
            lines[i:i + n] = new_lines
        new, count, how = "\n".join(lines), len(spans), f" (matched ignoring {name})"
    with open(p, "w", encoding="utf-8") as f:
        f.write(new)
    return f"Edited {path}: replaced {count if replace_all else 1} occurrence(s){how}"


def tool_write(path, content):
    p = resolve(path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    existed = os.path.exists(p)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return f"{'Overwrote' if existed else 'Created'} {path} ({len(content.encode())} bytes)"


SCHEMAS = {t["name"]: t["parameters"] for t in TOOLS}
TYPES = {"string": str, "integer": int, "boolean": bool}


def run_tool(name, raw_args):
    """執行一個工具呼叫，回傳 (文字, 是否錯誤)。所有錯誤都變成給模型看的文字。"""
    if name not in SCHEMAS:
        return f"Unknown tool: {name}. Available tools: {', '.join(TOOL_NAMES)}", True
    try:
        args = json.loads(raw_args or "{}", strict=False)
        if not isinstance(args, dict):
            raise ValueError("arguments must be a JSON object")
    except ValueError as e:
        # 把收到的原文回給模型，它才知道自己寫錯了哪裡
        return f"Invalid JSON arguments for {name}: {e}\nReceived: {(raw_args or '')[:2000]}", True
    schema = SCHEMAS[name]
    # Qwen 的工具呼叫是 XML 格式，參數值本來就是文字，數字和布林常以字串送來：能轉的先轉
    for k, v in args.items():
        want = (schema["properties"].get(k) or {}).get("type")
        if isinstance(v, str) and want == "integer" and v.strip().lstrip("-").isdigit():
            args[k] = int(v)
        elif isinstance(v, str) and want == "boolean" and v.strip().lower() in ("true", "false"):
            args[k] = v.strip().lower() == "true"
    missing = [k for k in schema["required"] if k not in args]
    unknown = [k for k in args if k not in schema["properties"]]
    wrong = [k for k, v in args.items() if k in schema["properties"]
             and not isinstance(v, TYPES[schema["properties"][k]["type"]])]
    if missing or unknown or wrong:
        parts = ([f"missing required: {', '.join(missing)}"] if missing else []) + \
                ([f"unknown: {', '.join(unknown)}"] if unknown else []) + \
                ([f"wrong type: {', '.join(wrong)}"] if wrong else [])
        return f"Invalid arguments for {name} ({'; '.join(parts)}). Received: {(raw_args or '')[:2000]}", True
    try:
        if name == "bash":
            return tool_bash(**args)
        return {"read": tool_read, "edit": tool_edit, "write": tool_write}[name](**args), False
    except ToolError as e:
        return str(e), True
    except Exception as e:   # 工具本身出錯（權限、編碼…）也回給模型
        return f"{name} failed: {type(e).__name__}: {e}", True


# ---------- 模型 ----------

class ModelError(Exception):
    pass


def chat(url, key, body, on_delta):
    """串流呼叫 Chat Completions，組回完整的回應。連線錯誤和 5xx 重試 3 次。"""
    req = urllib.request.Request(url + "/chat/completions", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    for attempt in range(4):
        try:
            resp = urllib.request.urlopen(req, timeout=600)
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:2000]
            if e.code < 500 or attempt == 3:
                raise ModelError(f"HTTP {e.code}: {detail}")
        except (urllib.error.URLError, OSError) as e:
            if attempt == 3:
                raise ModelError(f"connection failed: {e}")
        time.sleep(2 * 2 ** attempt)
    text, reasoning, calls, finish, usage, timings = [], [], {}, None, {}, {}
    with resp:
        for raw in resp:
            line = raw.decode(errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            if "error" in chunk:
                raise ModelError(json.dumps(chunk["error"], ensure_ascii=False))
            usage = chunk.get("usage") or usage
            timings = chunk.get("timings") or timings
            for choice in chunk.get("choices") or []:
                d = choice.get("delta") or {}
                if d.get("reasoning_content"):
                    reasoning.append(d["reasoning_content"])
                    on_delta("thinking", d["reasoning_content"])
                if d.get("content"):
                    text.append(d["content"])
                    on_delta("text", d["content"])
                for tc in d.get("tool_calls") or []:
                    c = calls.setdefault(tc.get("index", 0), {"id": None, "name": "", "arguments": ""})
                    c["id"] = tc.get("id") or c["id"]
                    f = tc.get("function") or {}
                    c["name"] += f.get("name") or ""
                    c["arguments"] += f.get("arguments") or ""
                finish = choice.get("finish_reason") or finish
    for c in calls.values():
        c["id"] = c["id"] or "call_" + uuid.uuid4().hex[:12]
    return {"text": "".join(text), "reasoning": "".join(reasoning), "calls": [calls[i] for i in sorted(calls)],
            "finish": finish, "usage": usage, "timings": timings}


# ---------- 迴圈 ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("prompt")
    ap.add_argument("--thinking", choices=["on", "off"], default="on")
    # chat template 預設只保留最後一則使用者訊息之後的思考；加這個旗標連更早的也保留（同 Pi 的做法）
    ap.add_argument("--preserve-thinking", action="store_true")
    ap.add_argument("--base-url", default=os.environ.get("MAIN_URL", "http://127.0.0.1:8080/v1"))
    ap.add_argument("--model", default=os.environ.get("MAIN_ALIAS", "qwen3.6-35b-a3b"))
    ap.add_argument("--ctx", type=int, default=int(os.environ.get("CTX") or 131072))
    args = ap.parse_args()
    key = os.environ.get("HARNESS_API_KEY") or os.environ.get("API_KEY") or "none"

    # 被 timeout 結束時，連同執行中的 bash 一起收掉（它在自己的程序群組，不會收到 timeout 的訊號）
    def on_term(signum, _frame):
        if running:
            try:
                os.killpg(running.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        emit({"type": "agent_end", "reason": f"signal {signum}"})
        sys.exit(128 + signum)
    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGHUP, on_term)

    system = SYSTEM.format(cwd=os.getcwd(), platform=platform.system(), today=date.today().isoformat())
    tools = [{"type": "function", "function": t} for t in TOOLS]
    messages = [{"role": "system", "content": system}, {"role": "user", "content": args.prompt}]
    config = {"model": args.model, "base_url": args.base_url, "thinking": args.thinking,
              "preserve_thinking": args.preserve_thinking, "ctx": args.ctx,
              "sampling": SAMPLING[args.thinking], "max_tokens": MAX_TOKENS}
    emit({"type": "session", "harness": "harness", "cwd": os.getcwd(), "config": config, "system": system, "tools": TOOLS})
    emit({"type": "agent_start"})

    last_total, history, reason = 0, [], "max_steps"
    for step in range(MAX_STEPS):
        # 輸出上限不超過 context 剩下的空間（以上一回合的總長估計，留 4K 餘裕）
        max_tokens = max(4096, min(MAX_TOKENS, args.ctx - last_total - 4096))
        body = {"model": args.model, "messages": messages, "tools": tools, "stream": True,
                "stream_options": {"include_usage": True}, "parallel_tool_calls": False,
                "max_tokens": max_tokens, **SAMPLING[args.thinking],
                "chat_template_kwargs": {"enable_thinking": args.thinking == "on",
                                         "preserve_thinking": args.preserve_thinking}}
        state = {"kind": None}

        def on_delta(kind, delta):
            # 串流事件只給 watch-agent.py 即時顯示思考用，格式照 Pi
            if kind != state["kind"] and state["kind"] == "thinking":
                emit({"type": "message_update", "assistantMessageEvent": {"type": "thinking_end"}})
            if kind == "thinking":
                if state["kind"] != "thinking":
                    emit({"type": "message_update", "assistantMessageEvent": {"type": "thinking_start"}})
                emit({"type": "message_update", "assistantMessageEvent": {"type": "thinking_delta", "delta": delta}})
            state["kind"] = kind

        t0 = time.time()
        try:
            r = chat(args.base_url, key, body, on_delta)
        except ModelError as e:
            emit({"type": "message_end", "message": {"role": "assistant", "content": [], "stopReason": "error",
                                                     "errorMessage": str(e)}, "elapsed": round(time.time() - t0, 1)})
            reason = "model_error"
            break
        if state["kind"] == "thinking":
            emit({"type": "message_update", "assistantMessageEvent": {"type": "thinking_end"}})

        # usage：llama-server 的 timings 有快取命中數（cache_n）和實際算的 prompt token 數（prompt_n）
        u, tm = r["usage"], r["timings"]
        prompt_total = u.get("prompt_tokens", 0)
        cached = tm.get("cache_n", (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0))
        output = u.get("completion_tokens", 0)
        last_total = prompt_total + output
        truncated = r["finish"] == "length"
        stop = "length" if truncated else ("toolUse" if r["calls"] else "stop")
        content = ([{"type": "thinking", "thinking": r["reasoning"]}] if r["reasoning"] else []) + \
                  ([{"type": "text", "text": r["text"]}] if r["text"] else []) + \
                  [{"type": "toolCall", "id": c["id"], "name": c["name"], "arguments": c["arguments"]} for c in r["calls"]]
        emit({"type": "message_end", "message": {
            "role": "assistant", "content": content, "stopReason": stop,
            "usage": {"input": prompt_total - cached, "cacheRead": cached, "output": output}},
            "elapsed": round(time.time() - t0, 1)})

        # 歷史裡保留 reasoning_content：chat template 會把它放回 prompt，快取才對得上
        assistant = {"role": "assistant", "content": r["text"]}
        if r["reasoning"]:
            assistant["reasoning_content"] = r["reasoning"]
        if truncated:
            # 被輸出上限截斷：工具呼叫的參數可能不完整，一律不執行，請模型分小步重來。
            # 只能用 user 訊息告知（沒有對應的 tool call 可以回）；template 會因此丟掉這之前的思考
            messages.append(assistant)
            messages.append({"role": "user", "content":
                             f"Your previous response was cut off at the output limit ({max_tokens} tokens), so its tool calls were not run. "
                             "Continue the task in smaller steps (for example, write a large file in several parts)."})
            continue
        if not r["calls"]:
            reason = "done"
            break
        assistant["tool_calls"] = [{"id": c["id"], "type": "function",
                                    "function": {"name": c["name"], "arguments": c["arguments"]}} for c in r["calls"]]
        messages.append(assistant)
        for c in r["calls"]:
            sig = (c["name"], c["arguments"])
            history.append(sig)
            emit({"type": "tool_execution_start", "toolCallId": c["id"], "toolName": c["name"], "args": c["arguments"]})
            t1 = time.time()
            if history[-REPEAT_LIMIT:] == [sig] * REPEAT_LIMIT:
                out, err = (f"Not run: this exact {c['name']} call was made {REPEAT_LIMIT - 1} times in a row already. "
                            "Its result will not change; try a different approach."), True
            else:
                out, err = run_tool(c["name"], c["arguments"])
            emit({"type": "tool_execution_end", "toolCallId": c["id"], "toolName": c["name"],
                  "result": [{"type": "text", "text": out}], "isError": err, "elapsed": round(time.time() - t1, 1)})
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": out})

    emit({"type": "agent_end", "reason": reason, "steps": step + 1})
    return 0 if reason == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
