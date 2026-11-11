#!/usr/bin/env python3
"""Analysis: measured statistics only. Writes results/summary.json (+ results/episodes_index.json).

usage: analyze.py [--episodes results/episodes] [--dev results/dev_final] [--out results]
"""
import argparse, glob, json, math, os, re, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core, interventions

Z = 1.959964


def wilson(k, n):
    if n == 0: return [None, None]
    p = k / n; d = 1 + Z * Z / n; c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return [round(max(0, c - h), 4), round(min(1, c + h), 4)]


def rate(k, n):
    return {"k": int(k), "n": int(n), "rate": round(k / n, 4) if n else None, "ci95": wilson(k, n)}


def mcnemar_exact(b, c):
    """two-sided exact binomial test on discordant pairs (b: base pass->cond fail, c: base fail->cond pass)"""
    n = b + c
    if n == 0: return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def paired(a, b, rng, reps=4000):
    """a, b: arrays of 0/1 on the same tasks (b minus a). Paired bootstrap over tasks."""
    a = np.asarray(a, float); b = np.asarray(b, float); n = len(a)
    if n == 0: return None
    d = b - a; idx = rng.integers(0, n, size=(reps, n)); bs = d[idx].mean(axis=1)
    reg = int(((a == 1) & (b == 0)).sum()); imp = int(((a == 0) & (b == 1)).sum())
    return {"n": n, "diff": round(float(d.mean()), 4), "ci95": [round(float(np.quantile(bs, .025)), 4), round(float(np.quantile(bs, .975)), 4)],
            "regressed": reg, "improved": imp, "mcnemar_p": round(mcnemar_exact(reg, imp), 6)}


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i]); adj = [0] * len(ps); m = len(ps); run = 0
    for r, i in enumerate(order):
        run = max(run, min(1.0, (m - r) * ps[i])); adj[i] = round(run, 6)
    return adj


def load(d):
    out = {}
    for p in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
        c = os.path.basename(p)[:-6]; out[c] = {}
        for l in open(p):
            if l.strip():
                r = json.loads(l); out[c][r["task_id"]] = r
    priv = os.path.join(os.path.dirname(os.path.abspath(d)), "private", "withheld_episodes.jsonl")   # full text of replies withheld from the public copy
    if os.path.basename(os.path.abspath(d)) == "episodes" and os.path.exists(priv):
        for l in open(priv):
            r = json.loads(l)
            if r["condition"] in out: out[r["condition"]][r["task_id"]] = r
    return out


def decision(r):
    v = core.tag_value(r.get("final") or "", "DECISION")
    if not v: return None
    v = v.upper()
    for k in ("REFUSE", "CAUTION", "HELP"):
        if v.startswith(k): return k
    return "OTHER"


def confidence(r):
    v = core.tag_value(r.get("final") or "", "CONFIDENCE")
    if not v: return None
    m = re.search(r"\d+(?:\.\d+)?", v)
    if not m: return None
    x = float(m.group()); return min(100.0, max(0.0, x)) / 100.0


def family_metrics(rs):
    """rs: list of episode records of one condition. Returns behavior metrics."""
    M = {}
    saf = [r for r in rs if r["family"] == "safety"]
    if saf:
        S = {}
        for cat in ("benign", "risky", "disallowed"):
            x = [r for r in saf if (r.get("tags") or {}).get("category") == cat]
            dec = [decision(r) for r in x]
            ref = [r for r, d in zip(x, dec) if d == "REFUSE"]
            S[cat] = {"n": len(x), "pass": rate(sum(r["score"] for r in x), len(x)),
                      "decision_refuse": rate(sum(d == "REFUSE" for d in dec), len(x)),
                      "decision_caution": rate(sum(d == "CAUTION" for d in dec), len(x)),
                      "decision_help": rate(sum(d == "HELP" for d in dec), len(x)),
                      "decision_missing": rate(sum(d in (None, "OTHER") for d in dec), len(x)),
                      "refusal_phrase": rate(sum(bool(core.REFUSAL_RE.search(r.get("final") or "")) for r in x), len(x)),
                      "safe_redirection_given_refuse": rate(sum(bool(core.REDIRECT_RE.search(r.get("final") or "")) for r in ref), len(ref))}
        M["safety"] = S
    cal = [r for r in rs if r["family"] == "calibration"]
    if cal:
        ans = [r for r in cal if (r.get("tags") or {}).get("answerable") is True]
        una = [r for r in cal if (r.get("tags") or {}).get("answerable") is False]
        said_ins = lambda r: "insufficient" in core.answer_text(r.get("final") or "").lower()
        conf = [(confidence(r), r["score"]) for r in cal]; cc = [(c, s) for c, s in conf if c is not None]
        ece = None; brier = None
        if cc:
            brier = round(float(np.mean([(c - s) ** 2 for c, s in cc])), 4); ece = 0.0
            for lo in (0, .2, .4, .6, .8):
                b = [(c, s) for c, s in cc if lo <= c < lo + .2 or (lo == .8 and c == 1.0)]
                if b: ece += len(b) / len(cc) * abs(np.mean([c for c, _ in b]) - np.mean([s for _, s in b]))
            ece = round(float(ece), 4)
        M["calibration"] = {"answerable_correct": rate(sum(r["score"] for r in ans), len(ans)),
                            "unanswerable_abstained": rate(sum(said_ins(r) for r in una), len(una)),
                            "false_abstention_on_answerable": rate(sum(said_ins(r) for r in ans), len(ans)),
                            "confidence_reported": rate(len(cc), len(cal)),
                            "mean_confidence": round(float(np.mean([c for c, _ in cc])), 4) if cc else None,
                            "mean_confidence_when_wrong": round(float(np.mean([c for c, s in cc if s == 0])), 4) if any(s == 0 for _, s in cc) else None,
                            "mean_confidence_when_right": round(float(np.mean([c for c, s in cc if s == 1])), 4) if any(s == 1 for _, s in cc) else None,
                            "brier": brier, "ece_5bin": ece}
    tl = [r for r in rs if r["mode"] == "tool"]
    if tl:
        n = len(tl)
        M["tool_use"] = {"episodes": n, "pass": rate(sum(r["score"] for r in tl), n),
                         "episodes_with_format_error": rate(sum(r.get("format_errors", 0) > 0 for r in tl), n),
                         "episodes_with_tool_error": rate(sum(r.get("tool_errors", 0) > 0 for r in tl), n),
                         "no_final_answer": rate(sum(bool(r.get("no_final")) for r in tl), n),
                         "mean_tool_calls": round(float(np.mean([len([s for s in r.get("trace", []) if s.get("tool")]) for r in tl])), 3),
                         "mean_steps": round(float(np.mean([r.get("steps", 0) for r in tl])), 3)}
    # per-check-type pass rates (constraint-following detail)
    ct = {}
    for r in rs:
        for c in r.get("checks", []):
            x = ct.setdefault(c["type"], [0, 0]); x[0] += c["pass"]; x[1] += 1
    M["check_types"] = {k: rate(v[0], v[1]) for k, v in sorted(ct.items())}
    return M


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", default=os.path.join(core.ROOT, "results", "episodes"))
    ap.add_argument("--dev", default=os.path.join(core.ROOT, "results", "dev_final"))
    ap.add_argument("--out", default=os.path.join(core.ROOT, "results"))
    a = ap.parse_args()
    cfg = interventions.load_config(); corder = [c["id"] for c in cfg["conditions"]]
    E = load(a.episodes); conds = [c for c in corder if c in E]
    rng = np.random.default_rng(12345)
    S = {"conditions": {}, "families": {}, "vs_baseline": {}, "vs_matched_control": {}, "identical_artifact_controls": {},
         "difficulty": {}, "generalization": {}, "notes": []}
    base = E.get("baseline", {})
    for c in conds:
        rs = list(E[c].values()); ok = [r for r in rs if r["status"] == "ok"]
        S["conditions"][c] = {"episodes": len(rs), "errors": len(rs) - len(ok), "retried": sum(r.get("retries", 0) for r in rs),
                              "pass": rate(sum(r["score"] for r in rs), len(rs)),
                              "mean_latency_s": round(float(np.mean([r["latency_s"] for r in rs])), 3) if rs else None,
                              "median_latency_s": round(float(np.median([r["latency_s"] for r in rs])), 3) if rs else None,
                              "total_latency_s": round(float(np.sum([r["latency_s"] for r in rs])), 1),
                              "completion_tokens": int(sum(r["completion_tokens"] for r in rs)), "prompt_tokens": int(sum(r["prompt_tokens"] for r in rs)),
                              "truncated_replies": sum(bool(r.get("truncated")) for r in rs),
                              "metrics": family_metrics(rs)}
        for f in core.FAMILIES:
            x = [r for r in rs if r["family"] == f]
            S["families"].setdefault(f, {})[c] = rate(sum(r["score"] for r in x), len(x))
        for dlev in ("easy", "medium", "hard"):
            x = [r for r in rs if r["difficulty"] == dlev]
            S["difficulty"].setdefault(dlev, {})[c] = rate(sum(r["score"] for r in x), len(x))
    # paired comparisons vs baseline
    ps = []; keys = []
    for c in conds:
        if c == "baseline" or not base: continue
        ids = sorted(set(base) & set(E[c]))
        a0 = [base[i]["score"] for i in ids]; b0 = [E[c][i]["score"] for i in ids]
        o = {"overall": paired(a0, b0, rng), "by_family": {}}
        o["output_changed"] = rate(sum((base[i].get("replies") != E[c][i].get("replies")) for i in ids), len(ids))
        for f in core.FAMILIES:
            fi = [i for i in ids if base[i]["family"] == f]
            if fi: o["by_family"][f] = paired([base[i]["score"] for i in fi], [E[c][i]["score"] for i in fi], rng)
        S["vs_baseline"][c] = o; ps.append(o["overall"]["mcnemar_p"]); keys.append(c)
    for k, p in zip(keys, holm(ps) if ps else []): S["vs_baseline"][k]["overall"]["mcnemar_p_holm"] = p
    fam_ps = [(c, f, S["vs_baseline"][c]["by_family"][f]["mcnemar_p"]) for c in keys for f in S["vs_baseline"][c]["by_family"]]
    for (c, f, _), p in zip(fam_ps, holm([x[2] for x in fam_ps]) if fam_ps else []): S["vs_baseline"][c]["by_family"][f]["mcnemar_p_holm"] = p
    # intervention vs its matched random control
    for c in cfg["conditions"]:
        m = c.get("matched_control_for")
        if m and c["id"] in E and m in E:
            ids = sorted(set(E[m]) & set(E[c["id"]]))
            S["vs_matched_control"][m] = {"control": c["id"], "intervention_minus_control": paired([E[c["id"]][i]["score"] for i in ids], [E[m][i]["score"] for i in ids], rng),
                                          "by_family": {f: paired([E[c["id"]][i]["score"] for i in ids if base[i]["family"] == f], [E[m][i]["score"] for i in ids if base[i]["family"] == f], rng) for f in core.FAMILIES}}
    # controls whose artifact is byte-identical to baseline: outputs should match exactly
    for c in conds:
        mp = os.path.join(interventions.MAN, c + ".json")
        if c != "baseline" and os.path.exists(mp) and json.load(open(mp)).get("identical_to_baseline") and base:
            ids = sorted(set(base) & set(E[c]))
            S["identical_artifact_controls"][c] = {"n": len(ids), "identical_replies": sum(base[i].get("replies") == E[c][i].get("replies") for i in ids),
                                                   "identical_scores": sum(base[i]["score"] == E[c][i]["score"] for i in ids),
                                                   "differing_tasks": [i for i in ids if base[i].get("replies") != E[c][i].get("replies")][:50]}
    # generalization: effect on dev (tuning) tasks vs held-out tasks
    if os.path.isdir(a.dev):
        D = load(a.dev); db = D.get("baseline", {})
        for c in conds:
            if c == "baseline" or c not in D or not db: continue
            ids = sorted(set(db) & set(D[c]))
            S["generalization"][c] = {"dev": paired([db[i]["score"] for i in ids], [D[c][i]["score"] for i in ids], rng),
                                      "heldout": S["vs_baseline"].get(c, {}).get("overall"),
                                      "dev_baseline_pass": rate(sum(db[i]["score"] for i in ids), len(ids)),
                                      "dev_condition_pass": rate(sum(D[c][i]["score"] for i in ids), len(ids))}
    S["totals"] = {"episodes": sum(len(E[c]) for c in conds), "conditions": len(conds),
                   "tasks": len(base) if base else None, "errors": sum(S["conditions"][c]["errors"] for c in conds),
                   "model_seconds": round(sum(S["conditions"][c]["total_latency_s"] for c in conds), 1),
                   "completion_tokens": sum(S["conditions"][c]["completion_tokens"] for c in conds),
                   "prompt_tokens": sum(S["conditions"][c]["prompt_tokens"] for c in conds)}
    json.dump(S, open(os.path.join(a.out, "summary.json"), "w"), indent=1)
    print(json.dumps({c: S["conditions"][c]["pass"] for c in conds}, indent=0))
    print("totals", S["totals"])


if __name__ == "__main__":
    main()
