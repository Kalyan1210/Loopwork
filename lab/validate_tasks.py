#!/usr/bin/env python3
"""Validate a task file (JSON array). Objective gate used by agents and by the coordinator.

For every task: schema is checked, the `reference` response must PASS its own checks and the
`negative` response must FAIL them. Tool-mode references are replayed through the sandbox simulator.

usage: validate_tasks.py FILE.json [--family NAME] [--quiet]
exit code 0 only if every task is valid.
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core

REQ = ["local_id", "family", "subtheme", "difficulty", "mode", "checks", "reference", "negative"]


def validate_task(t, family=None):
    errs = []
    for k in REQ:
        if k not in t: errs.append(f"missing field '{k}'")
    if errs: return errs
    if t["family"] not in core.FAMILIES: errs.append("bad family")
    if family and t["family"] != family: errs.append(f"family must be {family}")
    if t["mode"] not in core.MODES: errs.append("bad mode")
    if t["difficulty"] not in ("easy", "medium", "hard"): errs.append("bad difficulty")
    mode = t["mode"]
    if mode == "multi":
        if not (isinstance(t.get("turns"), list) and 2 <= len(t["turns"]) <= 6 and all(isinstance(x, str) for x in t["turns"])):
            errs.append("multi mode needs 'turns': 2-6 strings")
        if not (isinstance(t["reference"], list) and len(t["reference"]) == len(t.get("turns", []))): errs.append("reference must be a list, one reply per turn")
        if not (isinstance(t["negative"], list) and len(t["negative"]) == len(t.get("turns", []))): errs.append("negative must be a list, one reply per turn")
    else:
        if not isinstance(t.get("prompt"), str) or len(t["prompt"]) < 10: errs.append("needs 'prompt' string")
        if mode == "tool":
            tools = t.get("tools")
            if not (isinstance(tools, list) and tools and all(x in core.TOOL_DOCS for x in tools)): errs.append("tool mode needs 'tools' from the fixed tool list")
            for k in ("reference", "negative"):
                if not isinstance(t[k], dict): errs.append(f"{k} must be {{'steps':[...],'final':...}}")
        else:
            for k in ("reference", "negative"):
                if not isinstance(t[k], str): errs.append(f"{k} must be a string")
    if not (isinstance(t["checks"], list) and t["checks"]): errs.append("checks must be a non-empty list")
    else:
        for c in t["checks"]:
            if not isinstance(c, dict) or c.get("type") not in core.CHECK_TYPES: errs.append(f"unknown check {c}")
    size = len(json.dumps([t.get("prompt"), t.get("turns"), t.get("system"), t.get("env")]))
    if size > 6000: errs.append(f"task too long ({size} chars of prompt/env; limit 6000)")
    if int(t.get("max_tokens", core.DEFAULT_MAX_TOKENS)) > core.HARD_MAX_TOKENS: errs.append("max_tokens over limit")
    if t["family"] == "safety" and (t.get("tags") or {}).get("category") not in ("benign", "risky", "disallowed"):
        errs.append("safety tasks need tags.category in benign|risky|disallowed")
    if t["family"] == "calibration" and not isinstance((t.get("tags") or {}).get("answerable"), bool):
        errs.append("calibration tasks need tags.answerable true|false")
    if errs: return errs
    try:
        ok = core.score_episode(t, core.reference_episode(t, t["reference"]))
        if ok["score"] != 1: errs.append("reference does NOT pass: " + json.dumps([c for c in ok["checks"] if not c["pass"]])[:300])
        bad = core.score_episode(t, core.reference_episode(t, t["negative"]))
        if bad["score"] != 0: errs.append("negative response PASSES the checks (checker too weak)")
    except Exception as ex:
        errs.append(f"exception while checking: {type(ex).__name__}: {ex}")
    return errs


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fam = sys.argv[sys.argv.index("--family") + 1] if "--family" in sys.argv else None
    tasks = json.load(open(args[0]))
    if not isinstance(tasks, list): print("file must be a JSON array"); sys.exit(2)
    bad = 0; seen = set()
    for t in tasks:
        errs = validate_task(t, fam) if isinstance(t, dict) else ["not an object"]
        lid = t.get("local_id") if isinstance(t, dict) else "?"
        if lid in seen: errs.append("duplicate local_id")
        seen.add(lid)
        if errs:
            bad += 1; print(f"INVALID {lid}: " + " | ".join(errs))
    print(f"{len(tasks) - bad}/{len(tasks)} valid")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
