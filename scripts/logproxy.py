#!/usr/bin/env python3
"""記錄用 proxy：聽 127.0.0.1:<listen>，把每個請求的 body 存到 <outdir>/NNN-<path>.json，再原封不動轉給 127.0.0.1:<upstream>。
回應（含 SSE 串流）邊收邊轉，用關閉連線標示結束。用來看 harness 實際送給模型的系統提示與訊息。
用法：scripts/logproxy.py <listen> <upstream> <outdir>
例：harness 設定寫死連 8080，所以伺服器改開在 8081，proxy 佔 8080：
  MAIN_PORT=8081 scripts/serve-main.sh &  scripts/logproxy.py 8080 8081 logs/runs/<題目>/<harness>/<時間>/requests"""
import http.client
import http.server
import itertools
import os
import sys
import threading

listen, upstream, outdir = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
os.makedirs(outdir, exist_ok=True)
counter = itertools.count(1)
lock = threading.Lock()
HOP = {"connection", "keep-alive", "transfer-encoding", "content-length", "host"}


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):
        pass

    def _forward(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        with lock:
            n = next(counter)
        if body:
            name = f"{n:03d}-{self.command}-{self.path.strip('/').replace('/', '_')[:40]}.json"
            with open(os.path.join(outdir, name), "wb") as f:
                f.write(body)
        conn = http.client.HTTPConnection("127.0.0.1", upstream, timeout=1800)
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        conn.request(self.command, self.path, body=body or None, headers=headers)
        resp = conn.getresponse()
        self.send_response(resp.status, resp.reason)
        for k, v in resp.getheaders():
            if k.lower() not in HOP:
                self.send_header(k, v)
        self.send_header("Connection", "close")
        self.end_headers()
        while True:
            chunk = resp.read1(65536)
            if not chunk:
                break
            self.wfile.write(chunk)
            self.wfile.flush()
        conn.close()

    do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = _forward


http.server.ThreadingHTTPServer(("127.0.0.1", listen), Handler).serve_forever()
