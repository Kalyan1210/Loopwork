#!/usr/bin/env python3
"""Live swarm dashboard server. Serves lab/dashboard.html and the durable event log.

  GET /                       dashboard
  GET /api/events?since=N     events N.. from swarm/events.jsonl (the only source of dashboard state)
  GET /api/episode?cond=&task= full stored episode (prompt, replies, tool trace, score)
"""
import json, os, sys, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "swarm", "events.jsonl")
EPDIR = os.path.join(ROOT, "results", "episodes")
_idx = {}  # cond -> (size, {task: offset})


def episode(cond, task):
    p = os.path.join(EPDIR, os.path.basename(cond) + ".jsonl")
    if not os.path.exists(p): return None
    size = os.path.getsize(p)
    if _idx.get(cond, (0, {}))[0] != size:
        m = {}; off = 0
        with open(p, "rb") as f:
            for line in f:
                try: m[json.loads(line)["task_id"]] = off
                except Exception: pass
                off += len(line)
        _idx[cond] = (size, m)
    off = _idx[cond][1].get(task)
    if off is None: return None
    with open(p, "rb") as f:
        f.seek(off); return json.loads(f.readline())


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code); self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "no-store"); self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            return self.send(200, open(os.path.join(ROOT, "lab", "dashboard.html"), "rb").read(), "text/html")
        if u.path.startswith("/report"):   # serve the static report folder so relative data files load
            rel = u.path[len("/report"):].lstrip("/") or "index.html"
            full = os.path.realpath(os.path.join(ROOT, "report", rel))
            if not full.startswith(os.path.realpath(os.path.join(ROOT, "report"))) or not os.path.isfile(full): return self.send(404, "{}")
            ct = {"html": "text/html", "js": "application/javascript", "png": "image/png", "css": "text/css", "mp4": "video/mp4", "json": "application/json"}.get(full.rsplit(".", 1)[-1], "application/octet-stream")
            return self.send(200, open(full, "rb").read(), ct)
        if u.path == "/api/events":
            since = int(q.get("since", ["0"])[0]); out = []
            if os.path.exists(LOG):
                with open(LOG) as f:
                    for i, line in enumerate(f):
                        if i >= since and line.strip():
                            try: out.append(json.loads(line))
                            except Exception: out.append({"ts": 0, "actor": "?", "actor_kind": "coordinator", "role": "", "status": "progress", "msg": "(unparseable event line)"})
            return self.send(200, json.dumps({"since": since, "events": out}))
        if u.path == "/api/episode":
            ep = episode(q.get("cond", [""])[0], q.get("task", [""])[0])
            return self.send(200 if ep else 404, json.dumps(ep or {"error": "not found"}))
        self.send(404, "{}")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8790
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
