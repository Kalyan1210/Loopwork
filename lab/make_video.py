#!/usr/bin/env python3
"""Build report/walkthrough.mp4 from real screenshots of the report and the recorded swarm replay.
Needs the dashboard server on port 8790, Google Chrome and ffmpeg. Captions quote numbers from results/summary.json."""
import json, os, subprocess, sys, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core
S = json.load(open(os.path.join(core.ROOT, "results", "summary.json"))); EF = json.load(open(os.path.join(core.ROOT, "swarm", "engine_facts.json")))
AU = json.load(open(os.path.join(core.ROOT, "results", "score_audit.json")))["totals"]
P = lambda c: S["conditions"][c]["pass"]["k"]; VM = S["vs_matched_control"]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; BASE = "http://localhost:8790/report/"
OUT = os.path.join(core.ROOT, "report", "assets", "video"); SECS = 7
pt = lambda x: f"{x * 100:+.1f}"
scenes = [
 ("card", "Qwen Behavior Lab", "Direct weight edits on a local Qwen3 1.7B model, measured on 1,000 held-out tasks under 10 conditions. 10,000 scored episodes."),
 ("index.html#top", "Overview", "The brief asked for 10,000 tasks per condition. This machine could run 1,000 per condition, so the total is 10,000 episodes with 0 errors."),
 ("index.html#conditions", "Conditions", "Baseline, five gain edits in blocks 10 to 17, two matched random controls, a no-op and a rollback. The original model file was never written to."),
 ("index.html#controls", "Controls", f"No-op and rollback gave identical replies on 1,000 of 1,000 tasks. The feed-forward edit scored {pt(VM['ffn_med']['intervention_minus_control']['diff'])} points against its random control; the attention edit {pt(VM['attn_med']['intervention_minus_control']['diff'])} (interval includes zero)."),
 ("index.html#results", "Results", f"Tasks passed out of 1,000: baseline {P('baseline')}, ffn_low {P('ffn_low')}, ffn_med {P('ffn_med')}, ffn_up_low {P('ffn_up_low')}, attn_low {P('attn_low')}, attn_med {P('attn_med')}, random controls {P('rand_ffn_med')} and {P('rand_attn_med')}."),
 ("index.html#families", "Families", "Ten task families of 100 tasks each. Every task ran under every condition with the same prompt, settings and checker."),
 ("index.html#behavior", "Behavior", "Safety decisions, calibration and tool-use metrics per condition. The unmodified model rarely chose REFUSE on disallowed fictional requests."),
 ("index.html#generalization", "Generalization", "Edit strengths were chosen on 100 dev tasks only. Directions held on the held-out tasks; dev overstated most effect sizes."),
 ("index.html#examples", "Examples", "Showcased input and output pairs are drawn by a seeded rule and labeled representative, edge case or failure."),
 ("index.html#task=math-047&cond=ffn_med", "Trace explorer", "Any of the 10,000 episodes can be opened: task, condition, exact intervention, reply, tool trace, checks and score."),
 ("index.html#analysis", "AI notes", f"Auditor agents re-judged {AU['n']} sampled episodes and agreed with the automatic score on {AU['agree']}. A verifier recomputed the statistics with 0 mismatches."),
 ("swarm_replay.html", "Agent swarm (replay)", f"{EF['total_ai_work_items']} AI subagent work items, at most {EF['concurrency_cap']} at once. Model runs were done by one script worker, not by AI agents."),
 ("card", "What this does and does not show", "The edits lower measured task success, mostly like a random change of the same size. Nothing here shows what any neuron or layer represents."),
]
frames = []
for i, (src, k, t) in enumerate(scenes):
    q = {"k": k, "t": t}
    if src == "card": q["card"] = "1"
    else:
        q["src"] = BASE + src
        if "replay" in src: q["replay"] = "1"
        if "#task=" in src: q["scroll"] = "xDetail"
    png = os.path.join(OUT, f"scene_{i:02d}.png")
    subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--window-size=1600,900", "--virtual-time-budget=12000", f"--screenshot={png}",
                    BASE + "assets/video/frame.html?" + urllib.parse.urlencode(q)], capture_output=True, timeout=120)
    assert os.path.exists(png), png; frames.append(png); print("shot", i, k)
lst = os.path.join(OUT, "frames.txt")
open(lst, "w").write("".join(f"file '{p}'\nduration {SECS}\n" for p in frames) + f"file '{frames[-1]}'\n")
mp4 = os.path.join(core.ROOT, "report", "walkthrough.mp4")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-vf", "fps=30,format=yuv420p,scale=1600:900", "-c:v", "libx264", "-crf", "20", "-movflags", "+faststart", mp4], check=True)
print("walkthrough.mp4", os.path.getsize(mp4) // 1024, "KB,", len(frames) * SECS, "s")
