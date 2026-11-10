#!/usr/bin/env python3
"""Pilot DEV tasks on the unmodified baseline model (difficulty/format calibration only).

Refuses any file not named dev*.json: held-out evaluation tasks must never be piloted,
so that task design and intervention tuning cannot leak into the evaluation set.

usage: pilot.py tasks/<family>/dev.json [--show]
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core

f = sys.argv[1]
if not os.path.basename(f).startswith("dev"):
    sys.exit("refused: only dev*.json files may be piloted (held-out eval tasks stay unseen)")
tasks = json.load(open(f)); tot = 0
for t in tasks:
    ep = core.run_episode(t, lambda m, n: core.complete(m, n))
    s = core.score_episode(t, ep); tot += s["score"]
    print(f"--- {t['local_id']} [{t['difficulty']}] score={s['score']} steps={ep['steps']} tok={ep['completion_tokens']} {ep['latency_s']}s")
    print("   fails:", [(c['type'], c['detail']) for c in s['checks'] if not c['pass']])
    if "--show" in sys.argv:
        for r in ep["replies"]: print("   reply:", r[:500].replace("\n", "\n          "))
print(f"baseline pilot: {tot}/{len(tasks)} passed")
