#!/usr/bin/env python3
"""把 harness 子 agent 的紀錄複製到 run 目錄的 subagents/（agent-test.sh 在 harness 結束後呼叫）。

主串流 agent.jsonl 只有主 agent 的事件，子 agent 的完整紀錄各 harness 存在別處：
  qwen      $QWEN_HOME/projects/<工作目錄>/subagents/<主 session id>/，加了 --chat-recording false 也會寫
  opencode  子 agent 是另一個 session，存在 opencode.db，用 opencode export <session id> 匯出成 JSON
  codex     每個 agent 一個 rollout 檔，在 $CODEX_HOME/sessions/（agent-test 不加 --ephemeral 才會寫）；
            挑執行期間新寫、cwd 是這次工作目錄、又不是主 agent 的那些
Claude Code 的子 agent 訊息本來就在串流裡（帶 parent_tool_use_id），Pi 沒有子 agent，都不用處理。

用法：scripts/collect-subagents.py <harness> <run 目錄> <工作目錄> <開始時間（epoch 秒）>
"""

import glob
import json
import os
import shutil
import subprocess
import sys

harness, run, work, start = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
out = os.path.join(run, "subagents")


def events():
    try:
        data = open(os.path.join(run, "agent.jsonl"), "rb").read()
    except OSError:
        return
    for raw in data.split(b"\n"):
        if raw.strip():
            try:
                yield json.loads(raw)
            except json.JSONDecodeError:
                pass


copied = []
if harness == "qwen":
    sid = next((e.get("session_id") for e in events()
                if e.get("type") == "system" and e.get("subtype") == "init"), None)
    if sid:
        for d in glob.glob(os.path.join(os.environ["QWEN_HOME"], "projects", "*", "subagents", sid)):
            shutil.copytree(d, out, dirs_exist_ok=True)
            copied += os.listdir(d)

elif harness == "opencode":
    ids = []
    for e in events():
        part = e.get("part") or {}
        if e.get("type") == "tool_use" and part.get("tool") == "task":
            sid = ((part.get("state") or {}).get("metadata") or {}).get("sessionId")
            if sid and sid not in ids:
                ids.append(sid)
    for sid in ids:
        try:
            r = subprocess.run(["opencode", "export", sid], cwd=work, capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            print(f"opencode export {sid} 逾時", file=sys.stderr)
            continue
        if r.returncode == 0 and r.stdout.strip():
            os.makedirs(out, exist_ok=True)
            with open(os.path.join(out, sid + ".json"), "wb") as f:
                f.write(r.stdout)
            copied.append(sid + ".json")

elif harness == "codex":
    main = next((e.get("thread_id") for e in events() if e.get("type") == "thread.started"), None)
    for f in glob.glob(os.path.join(os.environ["CODEX_HOME"], "sessions", "*", "*", "*", "rollout-*.jsonl")):
        if os.path.getmtime(f) < start:
            continue
        with open(f, "rb") as fh:
            first = fh.readline()
        try:
            meta = json.loads(first).get("payload") or {}
        except json.JSONDecodeError:
            continue
        if meta.get("cwd") == work and meta.get("id") != main:
            os.makedirs(out, exist_ok=True)
            shutil.copy2(f, out)
            copied.append(os.path.basename(f))

if copied:
    print(f"子 agent 紀錄 {len(copied)} 個 → {out}")
