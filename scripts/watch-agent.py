#!/usr/bin/env python3
"""即時顯示 agent 的對話：思考、回覆、工具呼叫與結果，跟著 run 目錄的 agent.jsonl 一路印下去。

用法：
  scripts/watch-agent.py RUN_DIR             看一個 run（可以是正在跑的），run 結束（出現 meta.json）就停
  scripts/agent-test.sh --monitor 題目 harness   跑測試時同時顯示（agent-test.sh 內部用 --pid）

harness 從 run 目錄的路徑判斷（logs/runs/<題目>/<harness>/<日期_時間>）。Pi 的思考邊產生邊印出全文，
其他 harness 的思考與所有工具結果只印開頭幾行（它們的紀錄只有整則完成的事件）。
"""

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

try:   # 有 rich（scripts/setup-tools.sh 裝在 .venv）就把回覆、思考當 Markdown 呈現，沒有就印純文字
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.padding import Padding
    from rich.text import Text
    console = Console(highlight=False)
except ImportError:
    console = None

THINK_LINES, THINK_CHARS = 8, 800
TEXT_LINES, TEXT_CHARS = 80, 4000
RESULT_LINES, RESULT_CHARS = 6, 600
STYLES = {"思考": "dim", "回覆": "bold green", "工具": "bold dark_cyan", "結果": "dim", "錯誤": "bold red", "警告": "bold yellow", "進度": "dim", "題目": "bold magenta"}
t0 = time.time()


def clip(s, lines, chars):
    """取開頭幾行、幾個字，有截掉就註明原本多長。"""
    s = (s or "").strip()
    rows = s.splitlines()
    cut = "\n".join(rows[:lines])[:chars]
    return cut if cut == s else cut + f"\n…（共 {len(rows)} 行、{len(s)} 字）"


def out(label, inline="", body=None, md=False, style=None):
    """印一則事件：標頭一行（時間、類別、簡短內容），需要時再加縮排的內文。
    md=True 的內文當 Markdown 呈現；其餘原樣印出，不解讀任何標記（工具輸出裡的 [ ]、* 不能被當成格式）。"""
    stamp = time.strftime("%M:%S", time.gmtime(time.time() - t0))
    if console is None:
        print(f"[{stamp} {label}] {inline}".rstrip(), flush=True)
        if body:
            print("    " + body.replace("\n", "\n    "), flush=True)
        return
    head = Text(f"[{stamp} {label}]", style=STYLES.get(label, ""))
    if inline:
        head.append(" " + inline)
    console.print(head)
    if body:
        content = Markdown(body, style=style or "") if md else Text(body, style=style or "")
        console.print(Padding(content, (0, 0, 0, 4)))


def think(text):
    if text and text.strip():
        out("思考", body=clip(text, THINK_LINES, THINK_CHARS), md=True, style="dim")


def say(text):
    if text and text.strip():
        out("回覆", body=clip(text, TEXT_LINES, TEXT_CHARS), md=True)


def tool(name, args):
    if isinstance(args, dict):
        if "command" in args:
            desc = args["command"] or ""
        elif "content" in args and ("path" in args or "file_path" in args):
            body = args["content"] or ""
            desc = f"{args.get('path') or args.get('file_path')}（寫入 {body.count(chr(10)) + 1} 行）"
        else:
            desc = json.dumps(args, ensure_ascii=False)
    else:
        desc = str(args)
    desc = desc.strip()
    if "\n" in desc or len(desc) > 120:   # 多行指令（heredoc 之類）放到內文，保留換行
        out("工具", name, body=clip(desc, RESULT_LINES * 2, RESULT_CHARS * 2), style="dark_cyan")
    else:
        out("工具", f"{name}: {desc}")


def result(text, error=False):
    out("錯誤" if error else "結果", body=clip(text, RESULT_LINES, RESULT_CHARS) or "（無輸出）",
        style="red" if error else "dim")


def text_of(content):
    """工具結果的內容可能是字串，也可能是 [{"type": "text", "text": ...}] 之類的區塊列表。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    if isinstance(content, dict):
        return text_of(content.get("content"))
    return ""


def stream(text):
    """邊產生邊印（Pi 的思考可能長達數萬字、好幾分鐘，等整則結束才印就什麼都看不到）。
    原樣輸出、灰色、每行縮排；串流中途無法當 Markdown 排版。"""
    text = text.replace("\n", "\n    ")
    sys.stdout.write(f"\033[2m{text}\033[0m" if sys.stdout.isatty() else text)
    sys.stdout.flush()


class Pi:
    def __init__(self):
        self.streamed = False   # 這則訊息的思考已經串流印過，message_end 時不再重印
        self.open = False       # 串流中的思考還沒換行收尾

    def close(self):
        if self.open:
            sys.stdout.write("\n")
            self.open = False

    def __call__(self, e):
        t = e.get("type")
        if t == "message_update":
            a = e.get("assistantMessageEvent") or {}
            if a.get("type") == "thinking_start":
                out("思考")
                stream("    ")
                self.streamed = self.open = True
            elif a.get("type") == "thinking_delta" and isinstance(a.get("delta"), str):
                stream(a["delta"])
            elif a.get("type") == "thinking_end":
                self.close()
        elif t == "message_end" and (e.get("message") or {}).get("role") == "assistant":
            msg = e["message"]
            self.close()   # 思考被截斷時沒有 thinking_end
            for b in msg.get("content") or []:
                if b.get("type") == "thinking" and not self.streamed:
                    think(b.get("thinking"))
                elif b.get("type") == "text":
                    say(b.get("text"))
                elif b.get("type") == "toolCall":
                    tool(b.get("name"), b.get("arguments"))
            self.streamed = False
            if msg.get("stopReason") == "length":
                out("錯誤", "回應被截斷：撞到輸出長度上限（maxTokens）")
            elif msg.get("stopReason") == "error":
                out("錯誤", f"回應出錯：{msg.get('errorMessage') or ''}")
        elif t == "tool_execution_end":
            result(text_of(e.get("result")), bool(e.get("isError")))


def codex(e):
    item = e.get("item") or {}
    kind = item.get("type")
    if e.get("type") in ("turn.failed", "error"):
        out("錯誤", json.dumps(e.get("error") or e.get("message") or e, ensure_ascii=False))
    elif e.get("type") == "item.started" and kind == "command_execution":
        tool("bash", {"command": item.get("command")})
    elif e.get("type") != "item.completed":
        return
    elif kind == "reasoning":
        think(item.get("text"))
    elif kind == "agent_message":
        say(item.get("text"))
    elif kind == "command_execution":
        result(item.get("aggregated_output"), item.get("exit_code") not in (None, 0))
    elif kind == "file_change":
        tool("file_change", ", ".join(f"{c.get('kind')} {c.get('path')}" for c in item.get("changes") or []))
    elif kind == "error":   # item 層級的 error 是不中斷執行的警告（例如不認得模型名稱）；真正失敗是 turn.failed
        out("警告", item.get("message", ""))
    elif kind:
        tool(kind, {k: v for k, v in item.items() if k not in ("id", "type")})


def opencode(e):
    part = e.get("part") or {}
    t = e.get("type")
    if t == "reasoning":
        think(part.get("text"))
    elif t == "text":
        say(part.get("text"))
    elif t == "tool_use":
        state = part.get("state") or {}
        tool(part.get("tool"), state.get("input"))
        exit_code = (state.get("metadata") or {}).get("exit")
        result(state.get("output") or state.get("error") or "", state.get("status") == "error" or exit_code not in (None, 0))


def anthropic_style(e):
    """Qwen Code 與 Claude Code 的 stream-json：assistant 訊息的內容區塊、user 訊息裡的 tool_result。"""
    msg = e.get("message") or {}
    if e.get("type") == "assistant":
        for b in msg.get("content") or []:
            if b.get("type") == "thinking":
                think(b.get("thinking"))   # Claude 的思考是加密的，內容為空，不印
            elif b.get("type") == "text":
                say(b.get("text"))
            elif b.get("type") == "tool_use":
                tool(b.get("name"), b.get("input"))
    elif e.get("type") == "user":
        for b in msg.get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                result(text_of(b.get("content")), bool(b.get("is_error")))


HANDLERS = {"pi": Pi, "pi-router": Pi, "harness": Pi, "codex": lambda: codex, "opencode": lambda: opencode,
            "qwen": lambda: anthropic_style, "claude": lambda: anthropic_style}


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", help="run 目錄")
    ap.add_argument("--pid", type=int, help="這個程序結束後，讀完剩下的內容就停（agent-test.sh 用）")
    args = ap.parse_args()
    run = Path(args.run).resolve()
    harness = run.parent.name
    if harness not in HANDLERS:
        ap.error(f"從路徑判斷不出 harness：{run}（應為 logs/runs/<題目>/<harness>/<日期_時間>）")
    handle = HANDLERS[harness]()
    # 實際送出的題目（agent-test.sh 存的，含自動加上的限時）：有些 harness 的紀錄裡沒有題目
    if (run / "prompt.md").exists():
        out("題目", body=(run / "prompt.md").read_text(), md=True, style="dim")
    path = run / "agent.jsonl"
    pos, buf = 0, b""
    while True:
        done = (args.pid and not alive(args.pid)) or (not args.pid and (run / "meta.json").exists())
        if path.exists():
            with open(path, "rb") as f:
                f.seek(pos)
                chunk = f.read()
                pos += len(chunk)
            # 嚴格以 LF 切行：Pi 的 JSON 裡可能有 U+2028 之類的字元
            lines = (buf + chunk).split(b"\n")
            buf = lines.pop()
            for raw in lines:
                try:
                    e = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                try:
                    handle(e)
                except Exception as err:   # 格式沒預料到的事件不該讓監看中斷
                    out("錯誤", f"解析事件失敗：{err}")
        if done:
            break
        time.sleep(0.5)


if __name__ == "__main__":
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)   # 接 head 之類提早關閉時安靜結束
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        pass
