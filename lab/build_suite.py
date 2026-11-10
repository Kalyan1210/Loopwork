#!/usr/bin/env python3
"""Coordinator-controlled merge of agent-written task files into the frozen suites.

Re-validates every task (reference must pass, negative must fail), takes the first 20 valid tasks of
each generator file (100 per family), assigns global ids and writes:
  tasks/suite_eval.jsonl  (held-out; never piloted)      tasks/suite_dev.jsonl (tuning only)
  manifests/suite.json    (counts, sha256, per-file provenance, dropped tasks)
"""
import hashlib, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core
from validate_tasks import validate_task

T = os.path.join(core.ROOT, "tasks")
PREFIX = {"planning": "plan", "tools": "tool", "constraints": "cons", "synthesis": "synt", "math": "math", "coding": "code",
          "ambiguity": "ambi", "calibration": "cali", "safety": "safe", "longhorizon": "long"}
KEEP = ["family", "subtheme", "difficulty", "mode", "system", "prompt", "turns", "tools", "env", "max_tokens", "max_steps", "checks", "tags"]


def load(p):
    try:
        x = json.load(open(p)); return x if isinstance(x, list) else []
    except Exception:
        return []


def main():
    ev, dev, man = [], [], {"families": {}, "dropped": []}
    for fam in core.FAMILIES:
        fm = {"files": {}, "eval": 0, "dev": 0}; n = 0
        for k in range(1, 6):
            f = os.path.join(T, fam, f"gen_{k}.json"); good = []
            for t in load(f):
                errs = validate_task(t, fam) if isinstance(t, dict) else ["not an object"]
                if errs: man["dropped"].append({"file": f"{fam}/gen_{k}.json", "local_id": (t or {}).get("local_id") if isinstance(t, dict) else None, "errors": errs[:2]})
                else: good.append(t)
            fm["files"][f"gen_{k}.json"] = {"valid": len(good), "used": min(20, len(good))}
            for t in good[:20]:
                n += 1
                rec = {"id": f"{PREFIX[fam]}-{n:03d}", "split": "eval", "source": f"{fam}/gen_{k}.json#{t['local_id']}"}
                rec.update({x: t[x] for x in KEEP if x in t}); ev.append(rec)
        fm["eval"] = n; d = 0
        for t in load(os.path.join(T, fam, "dev.json")):
            if isinstance(t, dict) and not validate_task(t, fam):
                d += 1
                rec = {"id": f"{PREFIX[fam]}-dev-{d:02d}", "split": "dev", "source": f"{fam}/dev.json#{t['local_id']}"}
                rec.update({x: t[x] for x in KEEP if x in t}); dev.append(rec)
        fm["dev"] = d; man["families"][fam] = fm
    for name, rows in (("suite_eval.jsonl", ev), ("suite_dev.jsonl", dev)):
        p = os.path.join(T, name)
        with open(p, "w") as f:
            for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
        man[name] = {"n": len(rows), "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest()}
    json.dump(man, open(os.path.join(core.ROOT, "manifests", "suite.json"), "w"), indent=1)
    for fam, fm in man["families"].items(): print(f"{fam:12s} eval={fm['eval']:3d} dev={fm['dev']:2d} files={ {k: v['valid'] for k, v in fm['files'].items()} }")
    print("eval", len(ev), "dev", len(dev), "dropped", len(man["dropped"]))


if __name__ == "__main__":
    main()
