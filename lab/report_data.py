#!/usr/bin/env python3
"""Prepare the data files consumed by report/index.html (all measured; nothing synthesized).

Writes  report/data/lab.js            window.LAB = {...}   summary, manifests, task index, score matrix, examples
        report/data/traces_<fam>.js   window.TRACES[fam] = {task_id: {task, eps: {condition: episode}}}
        report/swarm_replay.html      dashboard with the recorded event log embedded (replay mode)
Example selection is rule-based and seeded (see pick_examples) so nothing is hand-picked silently.
"""
import glob, json, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core, interventions, redact_public
from analyze import load

R = os.path.join(core.ROOT, "report"); D = os.path.join(R, "data")


def jread(p, default=None):
    try: return json.load(open(p))
    except Exception: return default


def slim(r):
    r = redact_public.redact_record(r)   # safety-flagged reply bodies are never published in the report
    return {k: r.get(k) for k in ("status", "error", "score", "checks", "replies", "final", "trace", "final_env", "latency_s", "completion_tokens",
                                  "prompt_tokens", "steps", "format_errors", "tool_errors", "no_final", "truncated", "retries", "block", "withheld")}


def pick_examples(E, conds, tasks):
    """Seeded, rule-based showcase. Labels say how each example was chosen."""
    rng = random.Random(7); base = E.get("baseline", {}); out = []
    ids = sorted(base)
    for c in conds:
        if c == "baseline" or not ids: continue
        common = [i for i in ids if i in E[c]]
        reg = [i for i in common if base[i]["score"] == 1 and E[c][i]["score"] == 0]
        imp = [i for i in common if base[i]["score"] == 0 and E[c][i]["score"] == 1]
        same = [i for i in common if base[i]["score"] == E[c][i]["score"]]
        for i in rng.sample(common, min(3, len(common))):
            out.append({"task": i, "condition": c, "label": "representative", "how": "uniform random draw from all tasks of this condition (seed 7), regardless of outcome"})
        for i in rng.sample(reg, min(2, len(reg))):
            out.append({"task": i, "condition": c, "label": "failure", "how": f"random draw from the {len(reg)} tasks that pass at baseline and fail here (regressions)"})
        for i in rng.sample(imp, min(2, len(imp))):
            out.append({"task": i, "condition": c, "label": "edge case", "how": f"random draw from the {len(imp)} tasks that fail at baseline and pass here (improvements)"})
        for i in rng.sample(same, min(1, len(same))):
            out.append({"task": i, "condition": c, "label": "representative", "how": f"random draw from the {len(same)} tasks whose score is unchanged vs baseline"})
    for x in out: x["family"] = tasks[x["task"]]["family"]
    return out


def main():
    os.makedirs(D, exist_ok=True)
    cfg = interventions.load_config()
    E = load(os.path.join(core.ROOT, "results", "episodes"))
    conds = [c["id"] for c in cfg["conditions"] if c["id"] in E]
    suite = [json.loads(l) for l in open(os.path.join(core.ROOT, "tasks", "suite_eval.jsonl"))]
    tasks = {t["id"]: t for t in suite}
    scores = {c: {i: (r["score"] if r["status"] == "ok" else -1) for i, r in E[c].items()} for c in conds}
    base = E.get("baseline", {})
    changed = {c: {i: int(base[i].get("replies") != r.get("replies")) for i, r in E[c].items() if i in base} for c in conds if c != "baseline"}
    events = [json.loads(l) for l in open(os.path.join(core.ROOT, "swarm", "events.jsonl")) if l.strip()]
    ai = {}
    for e in events:
        if e["actor_kind"] == "ai_subagent": ai.setdefault(e["actor"], []).append(e)
    act = set(); peak = 0
    for e in events:
        if e["actor_kind"] != "ai_subagent": continue
        if e["status"] == "started": act.add(e["actor"])
        elif e["status"] in ("done", "failed"): act.discard(e["actor"])
        peak = max(peak, len(act))
    swarm = {"ai_subagents_seen": len(ai), "ai_done": sum(any(e["status"] == "done" for e in v) for v in ai.values()),
             "ai_failed": sum(any(e["status"] == "failed" for e in v) and not any(e["status"] == "done" for e in v) for v in ai.values()),
             "peak_concurrent_self_reported": peak, "events": len(events),
             "by_role": {}, "engine": jread(os.path.join(core.ROOT, "swarm", "engine_facts.json"), {})}
    for a, v in ai.items():
        swarm["by_role"][v[0]["role"]] = swarm["by_role"].get(v[0]["role"], 0) + 1
    LAB = {"generated_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S %z"),
           "summary": jread(os.path.join(core.ROOT, "results", "summary.json"), {}),
           "inventory": jread(os.path.join(core.ROOT, "manifests", "baseline.json"), {}),
           "config": cfg, "manifests": {c: jread(os.path.join(interventions.MAN, c + ".json"), {}) for c in conds},
           "suite": jread(os.path.join(core.ROOT, "manifests", "suite.json"), {}),
           "tuning": jread(os.path.join(core.ROOT, "manifests", "tuning.json"), {}),
           "conditions": [{"id": c["id"], "type": c["type"], "label": c["label"]} for c in cfg["conditions"] if c["id"] in E],
           "families": core.FAMILIES,
           "tasks": [{"id": t["id"], "family": t["family"], "difficulty": t["difficulty"], "subtheme": t.get("subtheme"), "mode": t["mode"],
                      "tags": t.get("tags") or {}} for t in suite],
           "scores": scores, "changed": changed, "examples": pick_examples(E, conds, tasks),
           "analyst": jread(os.path.join(core.ROOT, "results", "analyst_findings.json"), {}),
           "audit": jread(os.path.join(core.ROOT, "results", "score_audit.json"), {}),
           "findings_html": (open(os.path.join(core.ROOT, "results", "findings.html")).read() if os.path.exists(os.path.join(core.ROOT, "results", "findings.html")) else None),
           "swarm": swarm}
    open(os.path.join(D, "lab.js"), "w").write("window.LAB = " + json.dumps(LAB, ensure_ascii=False) + ";\n")
    for f in core.FAMILIES:
        tr = {}
        for t in suite:
            if t["family"] != f: continue
            spec = {"prompt_shown": None, "system": t.get("system"), "checks": t["checks"], "mode": t["mode"], "tools": t.get("tools"), "source": t.get("source")}
            eps = {}
            for c in conds:
                r = E[c].get(t["id"])
                if r: eps[c] = slim(r); spec["prompt_shown"] = spec["prompt_shown"] or r.get("prompt_shown")
            tr[t["id"]] = {"task": spec, "eps": eps}
        open(os.path.join(D, f"traces_{f}.js"), "w").write(f"window.TRACES = window.TRACES || {{}}; window.TRACES[{json.dumps(f)}] = " + json.dumps(tr, ensure_ascii=False) + ";\n")
    dash = open(os.path.join(core.ROOT, "lab", "dashboard.html")).read()
    inject = "<script>window.SWARM_REPLAY = " + json.dumps({"events": events}, ensure_ascii=False).replace("</", "<\\/") + ";</script>\n<script>"
    i = dash.rindex("<script>")
    open(os.path.join(R, "swarm_replay.html"), "w").write(dash[:i] + inject + dash[i + len("<script>"):])
    print("lab.js", os.path.getsize(os.path.join(D, "lab.js")) // 1024, "KB; traces", sum(os.path.getsize(p) for p in glob.glob(os.path.join(D, "traces_*.js"))) // 1024, "KB; events", len(events))


if __name__ == "__main__":
    main()
