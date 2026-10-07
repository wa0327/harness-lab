#!/usr/bin/env python3
"""比較 agent-test.sh 的執行結果：token、回合、工具呼叫、程式差異、最終回覆。

用法：
  scripts/compare-runs.py RUN_DIR [RUN_DIR ...]   指定要比較的 run 目錄（在 logs/runs/ 下）
  scripts/compare-runs.py --latest TASK           每種 harness 取該題最新一次
  scripts/compare-runs.py --latest TASK --md      輸出 Markdown（預設是終端機用的對齊表格）
  scripts/compare-runs.py --final RUN_DIR         只印最終回覆（agent-test.sh 內部使用）

需要 run 目錄裡有 agent.jsonl（agent-test.sh 以 JSON 模式執行後才會有）。
"""

import argparse
import difflib
import hashlib
import json
import os
import sys
import unicodedata
from collections import Counter
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = Path(os.environ.get("LOG_DIR") or LAB_DIR / "logs")
CODEX_TOOL_ITEMS = {"command_execution", "file_change", "mcp_tool_call", "web_search", "todo_list"}


def load_events(path):
    """嚴格以 LF 切 JSONL（Pi 文件要求不能用會切 Unicode 分隔符的讀法）。"""
    events = []
    if not path.exists():
        return events
    for raw in path.read_bytes().split(b"\n"):
        raw = raw.rstrip(b"\r")
        if not raw.strip():
            continue
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            pass
    return events


def parse_pi(events):
    m = {"requests": 0, "prompt": 0, "cached": 0, "output": 0, "reasoning": None,
         "thinking_chars": 0, "tools": Counter(), "tool_errors": 0, "final": ""}
    for e in events:
        if e.get("type") == "message_end" and e.get("message", {}).get("role") == "assistant":
            msg = e["message"]
            u = msg.get("usage") or {}
            m["requests"] += 1
            m["prompt"] += u.get("input", 0) + u.get("cacheRead", 0)
            m["cached"] += u.get("cacheRead", 0)
            m["output"] += u.get("output", 0)
            texts = []
            for block in msg.get("content") or []:
                if block.get("type") == "thinking":
                    m["thinking_chars"] += len(block.get("thinking") or "")
                elif block.get("type") == "text":
                    texts.append(block.get("text") or "")
            if texts:
                m["final"] = "".join(texts)
        elif e.get("type") == "tool_execution_end":
            m["tools"][e.get("toolName", "?")] += 1
            m["tool_errors"] += bool(e.get("isError"))
    return m


def parse_codex(events):
    m = {"requests": None, "prompt": 0, "cached": 0, "output": 0, "reasoning": 0,
         "thinking_chars": 0, "tools": Counter(), "tool_errors": 0, "final": ""}
    for e in events:
        if e.get("type") == "turn.completed":
            u = e.get("usage") or {}
            m["prompt"] += u.get("input_tokens", 0)
            m["cached"] += u.get("cached_input_tokens", 0)
            m["output"] += u.get("output_tokens", 0)
            m["reasoning"] += u.get("reasoning_output_tokens", 0)
        elif e.get("type") == "item.completed":
            item = e.get("item") or {}
            kind = item.get("type") or item.get("item_type")
            if kind == "reasoning":
                m["thinking_chars"] += len(item.get("text") or "")
            elif kind == "agent_message":
                # Codex 不回報請求次數；它每次回應都會先說一句話，以 agent_message 數估算
                m["requests"] = (m["requests"] or 0) + 1
                m["final"] = item.get("text") or m["final"]
            elif kind in CODEX_TOOL_ITEMS:
                m["tools"][kind] += 1
                failed = item.get("status") == "failed" or item.get("exit_code") not in (None, 0)
                m["tool_errors"] += failed
    return m


def load_run(run):
    run = Path(run).resolve()
    meta_path = run / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    harness = meta.get("harness") or ("codex" if "-codex-" in run.name else "pi")
    events = load_events(run / "agent.jsonl")
    parsed = parse_codex(events) if harness == "codex" else parse_pi(events)
    if not events:
        parsed = None
    task = meta.get("task") or run.name.rsplit(f"-{harness}-", 1)[0]
    return {"dir": run, "meta": meta, "harness": harness, "task": task,
            "label": meta.get("label", harness), "m": parsed}


def solution_files(r):
    """題目裡會被 agent 改動的檔案：排除測試、提示與規格。"""
    task_dir = LAB_DIR / "evals" / r["task"]
    names = sorted(p.name for p in task_dir.glob("*.py") if not p.name.startswith("test_"))
    return task_dir, names


def fmt(v):
    if v is None:
        return "—"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def table_rows(runs):
    ms = [r["m"] or {} for r in runs]
    approx = ["≈" if r["harness"] == "codex" and m.get("requests") else "" for r, m in zip(runs, ms)]
    return [
        ("結果", [r["meta"].get("verdict") for r in runs]),
        ("秒數", [int(r["meta"]["secs"]) if r["meta"].get("secs") else None for r in runs]),
        ("模型回應次數", [a + fmt(m.get("requests")) if m.get("requests") else None for a, m in zip(approx, ms)]),
        ("送出 prompt 總量 (tok)", [m.get("prompt") for m in ms]),
        ("  其中快取命中", [m.get("cached") for m in ms]),
        ("生成量 (tok)", [m.get("output") for m in ms]),
        ("  其中思考 (tok)", [m.get("reasoning") or None for m in ms]),
        ("思考內容 (字元)", [m.get("thinking_chars") or None for m in ms]),
        ("工具呼叫次數", [sum(m["tools"].values()) if m else None for m in ms]),
        ("  明細", [", ".join(f"{k}×{v}" for k, v in m["tools"].most_common()) if m else None for m in ms]),
        ("  結束碼非 0", [m.get("tool_errors") for m in ms]),
    ]


NOTES = [
    "送出 prompt 總量：Pi = input + cacheRead；Codex = turn.completed 的 input_tokens（已含快取）。",
    "模型回應次數：Codex 不回報，以它每次回應前說的話（agent_message）估算，標 ≈。",
    "思考：llama.cpp 不回報思考 token 數；Codex 經 Responses API 拿不到思考內容，所以顯示 —。",
    "結束碼非 0：多半是第一次跑測試時測試失敗，題目本來就有 bug，屬預期。",
]


def col_titles(runs):
    return [(r["label"], r["dir"].name.rsplit("-", 2)[-2][4:] + "-" + r["dir"].name.rsplit("-", 1)[-1][:4])
            for r in runs]


def table_md(runs):
    head = "| 指標 | " + " | ".join(f"{a}<br>`{b}`" for a, b in col_titles(runs)) + " |\n|---|" + "---|" * len(runs)
    body = "\n".join(f"| {n.strip()} | " + " | ".join(fmt(v) for v in vals) + " |" for n, vals in table_rows(runs))
    return head + "\n" + body + "\n\n" + "\n".join(f"- {n}" for n in NOTES)


def width(s):
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def pad(s, w, right=False):
    gap = " " * (w - width(s))
    return gap + s if right else s + gap


def table_term(runs):
    rows = [(n, [fmt(v) for v in vals]) for n, vals in table_rows(runs)]
    titles = col_titles(runs)
    w0 = max(width(n) for n, _ in rows + [("指標", [])])
    ws = [max([width(a), width(b)] + [width(vals[i]) for _, vals in rows]) for i, (a, b) in enumerate(titles)]
    line = lambda l, m, r: l + m.join("─" * (w + 2) for w in [w0] + ws) + r
    out = [line("┌", "┬", "┐")]
    out.append("│ " + pad("指標", w0) + " │ " + " │ ".join(pad(a, w) for (a, _), w in zip(titles, ws)) + " │")
    out.append("│ " + pad("", w0) + " │ " + " │ ".join(pad(b, w) for (_, b), w in zip(titles, ws)) + " │")
    out.append(line("├", "┼", "┤"))
    for n, vals in rows:
        numeric = lambda v: v[:1].isdigit() or v[:1] in "≈—"
        out.append("│ " + pad(n, w0) + " │ " + " │ ".join(pad(v, w, numeric(v)) for v, w in zip(vals, ws)) + " │")
    out.append(line("└", "┴", "┘"))
    return "\n".join(out) + "\n\n" + "\n".join(f"  * {n}" for n in NOTES)


def colorize(diff_text):
    colors = {"+": "\033[32m", "-": "\033[31m", "@": "\033[36m"}
    lines = []
    for ln in diff_text.splitlines(keepends=True):
        c = colors.get(ln[:1]) if not ln.startswith(("+++", "---")) else "\033[1m"
        lines.append(f"{c}{ln.rstrip(chr(10))}\033[0m\n" if c else ln)
    return "".join(lines)


def diffs(runs, md=True):
    out = []
    groups = {}
    for r in runs:
        task_dir, names = solution_files(r)
        blob = b"".join((r["dir"] / n).read_bytes() for n in names if (r["dir"] / n).exists())
        groups.setdefault(hashlib.sha256(blob).hexdigest(), []).append(r["label"])
    if len(groups) == 1 and len(runs) > 1:
        out.append("所有 run 改出來的程式**完全相同**。\n")
    elif len(runs) > 1:
        out.append("改出來的程式分成 %d 種版本：%s\n" % (
            len(groups), "；".join("、".join(v) for v in groups.values())))
    seen = set()
    for r in runs:
        task_dir, names = solution_files(r)
        for n in names:
            new = (r["dir"] / n).read_text().splitlines(keepends=True)
            if "".join(new) in seen:
                continue
            seen.add("".join(new))
            old = (task_dir / n).read_text().splitlines(keepends=True)
            d = "".join(difflib.unified_diff(old, new, f"evals/{r['task']}/{n}", f"{r['label']}/{n}")) or "（未修改）\n"
            if md:
                out.append(f"#### {r['label']}：{n}（相對於題目原檔）\n\n```diff\n{d}```\n")
            else:
                body = colorize(d) if sys.stdout.isatty() else d
                out.append(f"── {r['label']}：{n}（相對於題目原檔）\n{body}")
    return "\n".join(out)


def finals(runs, md=True):
    out = []
    for r in runs:
        text = (r["m"] or {}).get("final") or ""
        for name in ("final.md", "agent.log"):   # agent.log 是舊格式的輸出
            if not text and (r["dir"] / name).exists():
                text = (r["dir"] / name).read_text()
        head = f"#### {r['label']}\n" if md else f"── {r['label']}"
        out.append(f"{head}\n{text.strip() or '（無）'}\n")
    return "\n".join(out)


def latest_runs(task):
    best = {}
    for d in sorted((LOG_DIR / "runs").glob(f"{task}-*")):
        if not (d / "meta.json").exists() or not (d / "agent.jsonl").exists():
            continue
        r = load_run(d)
        best[r["label"]] = r
    return list(best.values())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*")
    ap.add_argument("--latest", metavar="TASK")
    ap.add_argument("--final", metavar="RUN_DIR")
    ap.add_argument("--md", action="store_true", help="輸出 Markdown（預設是終端機用的對齊表格）")
    a = ap.parse_args()

    if a.final:
        print((load_run(a.final)["m"] or {}).get("final", ""))
        return
    runs = latest_runs(a.latest) if a.latest else [load_run(d) for d in a.runs]
    if not runs:
        sys.exit("沒有可比較的 run（需要含 agent.jsonl 的目錄）")
    missing = [r["dir"].name for r in runs if r["m"] is None]
    tasks = {r["task"] for r in runs}

    h1, h2 = ("# ", "## ") if a.md else ("", "")
    print(f"{h1}執行比較：{'、'.join(sorted(tasks))}\n")
    if missing:
        print(f"{'> ' if a.md else ''}以下 run 沒有 agent.jsonl（舊格式），token 與工具欄位無資料：{'、'.join(missing)}\n")
    print(table_md(runs) if a.md else table_term(runs))
    print(f"\n{h2}程式差異\n" if a.md else "\n━━ 程式差異 ━━\n")
    print(diffs(runs, a.md))
    print(f"{h2}最終回覆\n" if a.md else "━━ 最終回覆 ━━\n")
    print(finals(runs, a.md))


if __name__ == "__main__":
    main()
