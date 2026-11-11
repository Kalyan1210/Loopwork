#!/usr/bin/env python3
"""Withhold reply bodies of safety-flagged episodes from the public copy.

The safety reviewer (results/analysis/review_safety.json) flagged six fictional safety tasks where some
replies named real-world items in response to a harmful request. For those task ids the reply text is
replaced by its first line (the DECISION label) plus a notice and the sha256 of the original text.
Scores, checks, tokens and latency are untouched. Originals go to results/private/ (git-ignored);
lab/analyze.py overlays them when present, so local re-analysis uses the full text.
"""
import glob, hashlib, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core

WITHHELD = {"safe-018", "safe-019", "safe-020", "safe-072", "safe-096", "safe-100"}
MARK = "[reply body withheld from the public copy after safety review; sha256 of original text: %s]"


def redact_text(s):
    if not isinstance(s, str) or "withheld from the public copy" in s: return s
    first = s.split("\n", 1)[0][:60]
    return first + "\n" + MARK % hashlib.sha256(s.encode()).hexdigest()


def redact_record(r):
    if r.get("task_id", r.get("task")) not in WITHHELD: return r
    r = dict(r); r["withheld"] = True
    if isinstance(r.get("replies"), list): r["replies"] = [redact_text(x) for x in r["replies"]]
    if r.get("final") is not None: r["final"] = redact_text(r["final"])
    return r


def main():
    priv = os.path.join(core.ROOT, "results", "private"); os.makedirs(priv, exist_ok=True)
    keep = os.path.join(priv, "withheld_episodes.jsonl"); n = 0
    with open(keep, "a") as kf:
        for p in sorted(glob.glob(os.path.join(core.ROOT, "results", "episodes", "*.jsonl"))):
            out = []
            for l in open(p):
                r = json.loads(l)
                if r["task_id"] in WITHHELD and not r.get("withheld"):
                    kf.write(l if l.endswith("\n") else l + "\n"); r = redact_record(r); n += 1
                out.append(json.dumps(r, ensure_ascii=False))
            open(p, "w").write("\n".join(out) + "\n")
    for p in glob.glob(os.path.join(core.ROOT, "results", "audit_samples", "*.json")):
        a = json.load(open(p)); json.dump([redact_record(x) for x in a], open(p, "w"), indent=1, ensure_ascii=False)
    print("withheld", n, "episode replies; originals in", keep)


if __name__ == "__main__":
    main()
