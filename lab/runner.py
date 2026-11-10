#!/usr/bin/env python3
"""Experiment runner: every task x every condition, identical settings, randomized block order.

Design: tasks are split (seeded, stratified by family) into B blocks. Within each block the order of
conditions is shuffled (seeded) and the task order is identical for every condition. For each
(block, condition) a fresh llama-server is started on that condition's artifact, so every condition
sees the same cold-start state. Runs are resumable: finished (condition, task) pairs are skipped.

usage: runner.py --suite tasks/suite_eval.jsonl --out results/episodes [--blocks 10] [--conditions a,b] [--limit N]
"""
import argparse, json, os, random, signal, subprocess, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core, interventions
from emit import emit

ROOT = core.ROOT
WORKER = "run-worker-1"


def start_server(artifact, port, logf):
    p = subprocess.Popen(["llama-server", "-m", artifact, "--port", str(port)] + core.SERVER_ARGS,
                         stdout=logf, stderr=subprocess.STDOUT)
    for _ in range(240):
        if p.poll() is not None: raise RuntimeError("llama-server exited during startup")
        try:
            if b"ok" in urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2).read(): return p
        except Exception:
            time.sleep(0.5)
    p.kill(); raise RuntimeError("llama-server did not become healthy")


def stop_server(p):
    if p and p.poll() is None:
        p.send_signal(signal.SIGTERM)
        try: p.wait(15)
        except subprocess.TimeoutExpired: p.kill()


def prompt_shown(t):
    if t["mode"] == "multi": return "\n".join(f"[turn {i + 1}] {u}" for i, u in enumerate(t["turns"]))
    s = t["prompt"]
    if t["mode"] == "tool":
        s += "\n[tools] " + ", ".join(t.get("tools", []))
        if t.get("env"): s += "\n[sandbox] " + json.dumps(t["env"])[:1500]
    if t.get("system"): s = "[system] " + t["system"] + "\n" + s
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--blocks", type=int, default=10); ap.add_argument("--conditions", default="")
    ap.add_argument("--port", type=int, default=8792); ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--seed", type=int, default=20261109); ap.add_argument("--config", default=interventions.CONFIG)
    ap.add_argument("--quiet-events", action="store_true")
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    conds = [c for c in cfg["conditions"] if not a.conditions or c["id"] in a.conditions.split(",")]
    tasks = [json.loads(l) for l in open(a.suite) if l.strip()]
    if a.limit: tasks = tasks[:a.limit]
    os.makedirs(a.out, exist_ok=True); os.makedirs(os.path.join(ROOT, "artifacts", "logs"), exist_ok=True)

    # stratified blocks: shuffle within family, deal round-robin into blocks
    rng = random.Random(a.seed); byfam = {}
    for t in tasks: byfam.setdefault(t["family"], []).append(t)
    blocks = [[] for _ in range(a.blocks)]
    for f in sorted(byfam):
        ts = byfam[f][:]; rng.shuffle(ts)
        for i, t in enumerate(ts): blocks[i % a.blocks].append(t)
    for b in blocks: rng.shuffle(b)
    schedule = []
    for bi in range(a.blocks):
        order = conds[:]; rng.shuffle(order)
        schedule += [(bi, c) for c in order]

    done = {}
    for c in conds:
        p = os.path.join(a.out, c["id"] + ".jsonl"); done[c["id"]] = set()
        if os.path.exists(p):
            for l in open(p):
                try: done[c["id"]].add(json.loads(l)["task_id"])
                except Exception: pass
    manifests = {}
    for c in conds:
        mp = os.path.join(interventions.MAN, c["id"] + ".json")
        art = os.path.join(ROOT, "artifacts", c["id"] + ".gguf")
        if not (os.path.exists(mp) and os.path.exists(art)): interventions.build(c["id"], cfg)
        manifests[c["id"]] = json.load(open(mp))
        assert interventions.sha256(art) == manifests[c["id"]]["artifact_sha256"], "artifact checksum mismatch: " + c["id"]
    ev = (lambda *x, **k: None) if a.quiet_events else emit
    ev("run-plan", "script_worker", "run-plan", "progress", msg="run plan",
       data={"conditions": [{"id": c["id"], "type": c["type"], "label": c["label"]} for c in conds], "n_tasks": len(tasks),
             "blocks": a.blocks, "suite": a.suite, "seed": a.seed, "inference": core.INFER, "server_args": core.SERVER_ARGS})
    ev(WORKER, "script_worker", "run-execution", "started", msg=f"{len(conds)} conditions x {len(tasks)} tasks, {a.blocks} blocks, 1 worker (serial; GPU-bound)")
    t_start = time.time(); n_run = 0
    for si, (bi, c) in enumerate(schedule):
        cid = c["id"]; todo = [t for t in blocks[bi] if t["id"] not in done[cid]]
        if not todo: continue
        art = os.path.join(ROOT, "artifacts", cid + ".gguf")
        logf = open(os.path.join(ROOT, "artifacts", "logs", f"server_{cid}.log"), "a")
        srv = start_server(art, a.port, logf)
        ev(WORKER, "script_worker", "run-execution", "progress", item=f"block {bi + 1}/{a.blocks}", msg=f"condition {cid}: {len(todo)} tasks (slot {si + 1}/{len(schedule)})")
        out = open(os.path.join(a.out, cid + ".jsonl"), "a")
        try:
            for oi, t in enumerate(todo):
                rec = {"task_id": t["id"], "family": t["family"], "condition": cid, "block": bi, "order": oi,
                       "artifact_sha256": manifests[cid]["artifact_sha256"], "mode": t["mode"], "difficulty": t["difficulty"],
                       "subtheme": t.get("subtheme"), "tags": t.get("tags") or {}, "prompt_shown": prompt_shown(t)}
                err = None; ep = None; retries = 0
                for attempt in range(2):
                    try:
                        ep = core.run_episode(t, lambda m, n: core.complete(m, n, port=a.port, timeout=180)); err = None; break
                    except Exception as ex:
                        err = f"{type(ex).__name__}: {ex}"
                        if attempt == 0:
                            retries = 1
                            ev(WORKER, "script_worker", "model-run", "retried", item=t["id"], family=t["family"], msg=err[:120], data={"c": cid})
                            if srv.poll() is not None: srv = start_server(art, a.port, logf)
                rec["retries"] = retries
                if ep is None:
                    rec.update({"status": "error", "error": err, "score": 0, "checks": [], "replies": [], "trace": [], "final": "",
                                "latency_s": 0, "completion_tokens": 0, "prompt_tokens": 0, "steps": 0, "format_errors": 0, "tool_errors": 0, "no_final": False})
                else:
                    sc = core.score_episode(t, ep)
                    env = ep.pop("env", None)
                    rec.update(ep); rec.update(sc); rec["status"] = "ok"; rec["error"] = None
                    if env is not None: rec["final_env"] = {"kv": env.get("kv"), "files": env.get("files"), "outbox": env.get("outbox")}
                rec["ts"] = round(time.time(), 3)
                out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush(); done[cid].add(t["id"]); n_run += 1
                ev(WORKER, "script_worker", "model-run", "failed" if rec["status"] == "error" else "done", item=t["id"], family=t["family"],
                   data={"c": cid, "s": rec["score"], "l": rec["latency_s"], "k": rec["completion_tokens"], "b": bi})
        finally:
            out.close(); stop_server(srv); logf.close()
        el = time.time() - t_start
        print(f"[{si + 1}/{len(schedule)}] block {bi} {cid}: +{len(todo)} episodes, total {n_run}, {el / 60:.1f} min, {el / max(n_run, 1):.2f} s/ep", flush=True)
    ev(WORKER, "script_worker", "run-execution", "done", msg=f"{n_run} episodes in {(time.time() - t_start) / 60:.1f} min")


if __name__ == "__main__":
    main()
