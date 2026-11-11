#!/usr/bin/env python3
"""Evaluation-leakage audit for the Qwen Behavior Lab task suites.

For every family, compares each held-out task (tasks/<family>/gen_*.json) with every dev task
(tasks/<family>/dev.json) and with every other held-out task, on normalized prompt/turn text:

  * exact      - normalized texts are identical
  * jaccard    - token-set Jaccard similarity >= 0.8
  * difflib    - difflib.SequenceMatcher ratio >= 0.9

Flagged pairs are printed and written to a candidates file for human reading. Human decisions
(which flagged pairs are real duplicates/leaks, and which were rewritten) live in a decisions
JSON file and are merged into the final report.

usage:
  leakage_audit.py                      # scan, print flagged pairs, write candidates file
  leakage_audit.py --watch              # also list sub-threshold "watch" pairs (jaccard>=0.6 / ratio>=0.75)
  leakage_audit.py --core               # supplementary boilerplate-stripped pass (reading aid only)
  leakage_audit.py --report OUT.json --decisions DECISIONS.json
                                        # scan and write the per-family report

It only reads task files; it never modifies them.
"""
import argparse, glob, json, os, re, sys
from difflib import SequenceMatcher

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TASKS = os.path.join(ROOT, "tasks")
JACCARD_T, RATIO_T = 0.8, 0.9
WATCH_JACCARD_T, WATCH_RATIO_T = 0.6, 0.75


def task_text(t):
    """The text the model actually sees from the user side: prompt, or all scripted turns."""
    parts = []
    if isinstance(t.get("prompt"), str):
        parts.append(t["prompt"])
    if isinstance(t.get("turns"), list):
        parts.extend(x for x in t["turns"] if isinstance(x, str))
    return "\n".join(parts)


def normalize(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_family(fam):
    items = []
    d = os.path.join(TASKS, fam)
    files = [os.path.join(d, "dev.json")] + sorted(glob.glob(os.path.join(d, "gen_*.json")))
    for f in files:
        if not os.path.exists(f):
            continue
        split = "dev" if os.path.basename(f) == "dev.json" else "heldout"
        for i, t in enumerate(json.load(open(f))):
            norm = normalize(task_text(t))
            items.append({
                "file": os.path.relpath(f, ROOT), "split": split, "index": i,
                "local_id": t.get("local_id"), "subtheme": t.get("subtheme"),
                "mode": t.get("mode"), "norm": norm, "tokens": frozenset(norm.split()),
                "raw": task_text(t),
            })
    return items


def jaccard(a, b):
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def ratio(a, b, floor):
    """difflib ratio, with the cheap upper bounds used to skip hopeless pairs."""
    sm = SequenceMatcher(None, a, b, autojunk=False)
    if sm.real_quick_ratio() < floor or sm.quick_ratio() < floor:
        return None
    return sm.ratio()


def ref(x):
    return {"file": x["file"], "local_id": x["local_id"], "split": x["split"], "subtheme": x["subtheme"]}


def scan_family(fam, watch=False):
    items = load_family(fam)
    held = [x for x in items if x["split"] == "heldout"]
    dev = [x for x in items if x["split"] == "dev"]
    pairs = [(h, d) for h in held for d in dev]
    pairs += [(held[i], held[j]) for i in range(len(held)) for j in range(i + 1, len(held))]
    flagged, watched = [], []
    floor = WATCH_RATIO_T if watch else RATIO_T
    for a, b in pairs:
        exact = a["norm"] == b["norm"]
        jac = jaccard(a["tokens"], b["tokens"])
        rat = 1.0 if exact else ratio(a["norm"], b["norm"], floor)
        reasons = []
        if exact:
            reasons.append("exact")
        if jac >= JACCARD_T:
            reasons.append("jaccard")
        if rat is not None and rat >= RATIO_T:
            reasons.append("difflib")
        rec = {"kind": "heldout-vs-" + b["split"], "a": ref(a), "b": ref(b),
               "jaccard": round(jac, 4), "difflib": None if rat is None else round(rat, 4),
               "reasons": reasons}
        if reasons:
            flagged.append(rec)
        elif watch and (jac >= WATCH_JACCARD_T or (rat is not None and rat >= WATCH_RATIO_T)):
            watched.append(rec)
    return {"n_dev": len(dev), "n_heldout": len(held), "pairs_compared": len(pairs),
            "flagged": flagged, "watch": watched, "items": items}


def core_scan(fam, min_share=4, thresh=0.5, top=8):
    """Supplementary, boilerplate-robust pass (not part of the flag criteria).

    Family prompts share long format instructions that both inflate and mask lexical similarity.
    Here each prompt is split into sentences/lines, any sentence that occurs in >= min_share tasks
    of the family is dropped, and token-set Jaccard is recomputed on what is left (the task-specific
    core). Returns the top pairs with core Jaccard >= thresh for human reading.
    """
    items = load_family(fam)
    from collections import Counter
    def sents(x):
        return [normalize(p) for p in re.split(r"(?<=[.!?:])\s+|\n+", x["raw"]) if normalize(p)]
    cnt = Counter(s for x in items for s in set(sents(x)))
    for x in items:
        x["core"] = frozenset(" ".join(s for s in sents(x) if cnt[s] < min_share).split())
    held = [x for x in items if x["split"] == "heldout"]
    dev = [x for x in items if x["split"] == "dev"]
    pairs = [(h, d) for h in held for d in dev]
    pairs += [(held[i], held[j]) for i in range(len(held)) for j in range(i + 1, len(held))]
    out = []
    for a, b in pairs:
        j = jaccard(a["core"], b["core"])
        if j >= thresh:
            out.append({"kind": "heldout-vs-" + b["split"], "a": ref(a), "b": ref(b),
                        "core_jaccard": round(j, 4), "a_text": a["raw"], "b_text": b["raw"]})
    out.sort(key=lambda r: -r["core_jaccard"])
    return out[:top], len(out)


def key(rec):
    return "|".join([rec["a"]["file"], str(rec["a"]["local_id"]), rec["b"]["file"], str(rec["b"]["local_id"])])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--families", nargs="*")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--candidates", default=None, help="write flagged (+watch) pairs with full text here")
    ap.add_argument("--report", default=None)
    ap.add_argument("--decisions", default=None)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--core", action="store_true",
                    help="only run the supplementary boilerplate-stripped pass and print its top pairs")
    a = ap.parse_args()
    fams = a.families or sorted(f for f in os.listdir(TASKS) if os.path.isdir(os.path.join(TASKS, f)))
    decisions = json.load(open(a.decisions)) if a.decisions else {}
    report = {"method": {"text": "normalized prompt + scripted turns (lowercase, non-alphanumerics -> space)",
                         "flag_if": f"exact match OR token-set Jaccard >= {JACCARD_T} OR difflib ratio >= {RATIO_T}",
                         "comparisons": "each held-out task vs every dev task and vs every other held-out task, within family"},
              "families": {}, "totals": {}}
    if a.core:
        for fam in fams:
            top, n = core_scan(fam)
            print(f"##### {fam}: {n} pairs with core Jaccard >= 0.5")
            for r in top:
                print(f"=== {r['core_jaccard']} {r['kind']} {r['a']['file']}:{r['a']['local_id']} <> "
                      f"{r['b']['file']}:{r['b']['local_id']}")
                print("A:", r["a_text"][:330].replace("\n", " | "))
                print("B:", r["b_text"][:330].replace("\n", " | "))
        return 0
    cand = {}
    for fam in fams:
        r = scan_family(fam, watch=a.watch)
        text = {(x["file"], x["local_id"]): x["raw"] for x in r["items"]}
        if not a.quiet:
            print(f"{fam}: dev={r['n_dev']} heldout={r['n_heldout']} pairs={r['pairs_compared']} "
                  f"flagged={len(r['flagged'])} watch={len(r['watch'])}")
            for rec in r["flagged"]:
                print(f"  FLAG {rec['reasons']} jac={rec['jaccard']} dif={rec['difflib']} "
                      f"{rec['a']['file']}:{rec['a']['local_id']} <> {rec['b']['file']}:{rec['b']['local_id']}")
        cand[fam] = [dict(rec, level=lvl,
                          a_text=text[(rec["a"]["file"], rec["a"]["local_id"])],
                          b_text=text[(rec["b"]["file"], rec["b"]["local_id"])])
                     for lvl, lst in (("flag", r["flagged"]), ("watch", r["watch"])) for rec in lst]
        fd = decisions.get(fam, {})
        confirmed = fd.get("confirmed", [])
        report["families"][fam] = {
            "n_dev": r["n_dev"], "n_heldout": r["n_heldout"],
            "pairs_compared": r["pairs_compared"],
            # "flagged" is the count from the initial scan (before any rewrite) when the decisions
            # file records one; the current scan is always reported as flagged_after_rewrite.
            "flagged": len(fd["initial_flagged_pairs"]) if "initial_flagged_pairs" in fd else len(r["flagged"]),
            "confirmed": len(confirmed),
            "rewritten": len(fd.get("rewritten", [])),
            "confirmed_pairs": confirmed,
            "rewritten_tasks": fd.get("rewritten", []),
            "initial_flagged_pairs": fd.get("initial_flagged_pairs", r["flagged"]),
            "flagged_after_rewrite": len(r["flagged"]),
            "flagged_pairs_after_rewrite": r["flagged"],
            "notes": fd.get("notes", ""),
        }
    for k in ("pairs_compared", "flagged", "confirmed", "rewritten"):
        report["totals"][k] = sum(f[k] for f in report["families"].values())
    if a.candidates:
        json.dump(cand, open(a.candidates, "w"), indent=1)
    if a.report:
        for k in ("audit_summary", "sub_threshold_observations"):
            if k in decisions:
                report[k] = decisions[k]
        json.dump(report, open(a.report, "w"), indent=1)
        print("wrote", a.report, report["totals"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
