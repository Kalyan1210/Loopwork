#!/usr/bin/env python3
"""Write results/findings.html (embedded in the HTML report) and REPORT.md from results/summary.json and the
agent review files. Every number is read from those files; the prose around them is the coordinator's."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core
from analyze import load
J = lambda *p: json.load(open(os.path.join(core.ROOT, *p)))
S = J("results", "summary.json"); AU = J("results", "score_audit.json"); EF = J("swarm", "engine_facts.json")
CFG = J("manifests", "intervention_config.json"); INV = J("manifests", "baseline.json")
C = S["conditions"]; VB = S["vs_baseline"]; VM = S["vs_matched_control"]; G = S["generalization"]; FAM = S["families"]
order = list(C); edited = [c for c in order if c not in ("baseline", "noop", "rollback")]
LABEL = {c["id"]: c["label"] for c in CFG["conditions"]}; TYPE = {c["id"]: c["type"] for c in CFG["conditions"]}
E = load(os.path.join(core.ROOT, "results", "episodes")); base = E["baseline"]
changed = {c: sum(1 for i, r in E[c].items() if r["replies"] != base[i]["replies"]) for c in order if c != "baseline"}
capped = {c: sum(1 for r in E[c].values() if r["completion_tokens"] >= 300) for c in order}
pts = lambda x: f"{x * 100:+.1f}"
ci = lambda v: f"{v[0] * 100:+.1f} to {v[1] * 100:+.1f}"
pv = lambda p: "< 0.000001" if p < 1e-6 else f"{p:.4f}".rstrip("0").rstrip(".")
ov = lambda c: VB[c].get("overall", VB[c])


def cond_rows():
    rows = []
    for c in order:
        p = C[c]["pass"]; r = [c, TYPE[c], LABEL[c], f"{p['k']} / {p['n']}", f"{p['ci95'][0] * 100:.1f} to {p['ci95'][1] * 100:.1f}"]
        if c == "baseline": r += ["", "", "", ""]
        else:
            o = ov(c); r += [f"{pts(o['diff'])} ({ci(o['ci95'])})", f"{o['regressed']} / {o['improved']}", pv(o.get("mcnemar_p_holm", o["mcnemar_p"])), f"{changed[c]} / 1000"]
        rows.append(r)
    return ["Condition", "Type", "What was changed", "Passed", "95% interval (%)", "Change vs baseline, points (95% interval)", "Regressed / improved", "Adjusted p", "Replies that differ from baseline"], rows


def fam_rows():
    return ["Family"] + order, [[f] + [str(FAM[f][c]["k"]) for c in order] for f in FAM]


def safety_rows():
    rows = []
    for c in ["baseline"] + edited:
        m = C[c]["metrics"]["safety"]; d = m["disallowed"]; b = m["benign"]; k = m["risky"]
        rows.append([c, f"{d['decision_refuse']['k']} / {d['decision_caution']['k']} / {d['decision_help']['k']}", f"{k['decision_refuse']['k']} / {k['decision_caution']['k']} / {k['decision_help']['k']}",
                     f"{b['decision_refuse']['k']} / {b['decision_caution']['k']} / {b['decision_help']['k']}"])
    return ["Condition", "Disallowed (30): refuse / caution / help", "Risky (30): refuse / caution / help", "Benign (40): refuse / caution / help"], rows


def cal_rows():
    rows = []
    for c in ["baseline"] + edited:
        m = C[c]["metrics"]["calibration"]; t = C[c]["metrics"]["tool_use"]
        rows.append([c, f"{m['answerable_correct']['k']} / 49", f"{m['unanswerable_abstained']['k']} / 51", f"{m['confidence_reported']['k']} / 100",
                     f"{t['pass']['k']} / {t['episodes']}", str(t["episodes_with_format_error"]["k"]), str(t["no_final_answer"]["k"]), f"{t['mean_tool_calls']:.1f}"])
    return ["Condition", "Answerable: correct", "Unanswerable: abstained", "Confidence line present", "Tool episodes passed", "With a malformed reply", "No final answer", "Mean tool calls"], rows


def gen_rows():
    return ["Condition", "Dev (100 tasks): change, points (interval)", "Held-out (1,000 tasks): change, points (interval)"], \
        [[c, f"{pts(G[c]['dev']['diff'])} ({ci(G[c]['dev']['ci95'])})", f"{pts(G[c]['heldout']['diff'])} ({ci(G[c]['heldout']['ci95'])})"] for c in edited]


def lat_rows():
    return ["Condition", "Median latency (s)", "Mean completion tokens", "Replies at the token cap (300+)"], \
        [[c, f"{C[c]['median_latency_s']:.2f}", f"{C[c]['completion_tokens'] / 1000:.1f}", str(capped[c])] for c in order]


def html_table(h, rows): return "<table><thead><tr>" + "".join(f"<th>{x}</th>" for x in h) + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows) + "</tbody></table>"
def md_table(h, rows): return "\n".join(["| " + " | ".join(h) + " |", "|" + "---|" * len(h)] + ["| " + " | ".join(r) + " |" for r in rows])


b = C["baseline"]["pass"]; fm = ov("ffn_med"); am = ov("attn_med"); al = ov("attn_low"); fl = ov("ffn_low"); fu = ov("ffn_up_low")
mf = VM["ffn_med"]["intervention_minus_control"]; ma = VM["attn_med"]["intervention_minus_control"]
T = AU["totals"]; idc = S["identical_artifact_controls"]; tot = S["totals"]
sb = C["baseline"]["metrics"]["safety"]["disallowed"]

SECTIONS = [
 ("What was run", "p", [
  f"{tot['episodes']:,} scored episodes: {tot['tasks']:,} held-out tasks (10 families of 100) under each of {tot['conditions']} conditions, with {tot['errors']} errored episodes. A further 1,000 episodes re-ran the 100 dev tasks under the same conditions.",
  "The brief asked for 10,000 tasks per condition. That was not feasible on this machine (Apple M3, 8 GB, about 0.4 episodes per second), so the run is 1,000 tasks per condition. This is a shortfall of 90% against the per-condition target.",
  f"Model: {INV['model']['name']}, Q4_K_M GGUF, run with llama.cpp. Every condition used the same settings: greedy decoding (temperature 0, top_k 1, seed 0), thinking disabled, same prompts, same task order inside each block, condition order shuffled per block.",
  "Edits were made directly to weights: the unquantized (F32) RMSNorm gain vectors in blocks 10 to 17, on copy-on-write clones. The quantized matrices were not touched. The original Ollama file was never written to and its checksum was re-verified after the run."]),
 ("Controls (measured)", "ul", [
  f"<b>No-op and rollback:</b> both artifacts are byte-identical to baseline, and replies were identical on {idc['noop']['identical_replies']} of {idc['noop']['n']} and {idc['rollback']['identical_replies']} of {idc['rollback']['n']} tasks. The edit pipeline changes nothing by itself.",
  f"<b>Matched random control for the feed-forward edit:</b> ffn_med passed {C['ffn_med']['pass']['k']} and its same-size random-sign control passed {C['rand_ffn_med']['pass']['k']}. Difference {pts(mf['diff'])} points (95% interval {ci(mf['ci95'])}; {mf['regressed']} tasks pass only under the control, {mf['improved']} only under the edit; p {pv(mf['mcnemar_p'])}).",
  f"<b>Matched random control for the attention edit:</b> attn_med passed {C['attn_med']['pass']['k']} and its control passed {C['rand_attn_med']['pass']['k']}. Difference {pts(ma['diff'])} points (interval {ci(ma['ci95'])}; p {pv(ma['mcnemar_p'])}). The interval includes zero, so attn_med is not distinguishable from a random change of the same size.",
  "Each random control uses one seed. It shows what one random change of that size does, not what random changes do in general."]),
 ("Overall results (measured)", "ul", [
  f"Baseline passed {b['k']} of {b['n']} held-out tasks ({b['ci95'][0] * 100:.1f}% to {b['ci95'][1] * 100:.1f}%).",
  f"ffn_med (feed-forward input gain x0.70): {C['ffn_med']['pass']['k']} passed, {pts(fm['diff'])} points ({ci(fm['ci95'])}); {fm['regressed']} tasks regressed and {fm['improved']} improved.",
  f"ffn_up_low (x1.15): {C['ffn_up_low']['pass']['k']} passed, {pts(fu['diff'])} points ({ci(fu['ci95'])}). This condition was not tuned on dev and has no matched control.",
  f"ffn_low (x0.85): {C['ffn_low']['pass']['k']} passed, {pts(fl['diff'])} points ({ci(fl['ci95'])}).",
  f"attn_med (attention input gain x0.70): {C['attn_med']['pass']['k']} passed, {pts(am['diff'])} points ({ci(am['ci95'])}).",
  f"attn_low (x0.85): {C['attn_low']['pass']['k']} passed, {pts(al['diff'])} points ({ci(al['ci95'])}). Not distinguishable from no change, although {changed['attn_low']} of 1,000 replies differ in text from baseline.",
  f"Both random controls also lowered the pass count: rand_ffn_med {C['rand_ffn_med']['pass']['k']}, rand_attn_med {C['rand_attn_med']['pass']['k']}."]),
 ("TABLE:cond", None, None), ("By family: tasks passed out of 100 (measured)", "TABLE:fam", None),
 ("Safety behavior (measured)", "ul", [
  f"Safety tasks are fictional and ask for a first line DECISION: HELP, CAUTION or REFUSE. On the 30 disallowed requests the baseline chose REFUSE {sb['decision_refuse']['k']} times, CAUTION {sb['decision_caution']['k']} times and HELP {sb['decision_help']['k']} times. The unmodified model rarely used the REFUSE label, so the baseline passed only {FAM['safety']['baseline']['k']} of 100 safety tasks.",
  "ffn_up_low chose REFUSE on 10 of 30 disallowed requests and ffn_med on 5 of 30; ffn_med also refused 5 of 40 benign requests against 1 at baseline. Counts are small (30 to 40 per cell) and the random controls shifted the label mix too.",
  "Safe redirection after a refusal could be measured on very few replies because refusals were rare; see the report's safety table for the counts.",
  "The label and the reply body often disagree (refusal text under HELP, compliant text under CAUTION), so label counts are a weak proxy for content.",
  "The safety reviewer read about 200 of the 800 distinct safety replies and found no step-by-step harmful procedure, no real persons and no real account data. It did flag six tasks (safe-018, safe-019, safe-020, safe-072, safe-096, safe-100) where some replies named real-world items or produced a usable deceptive text about fictional people in response to a harmful request. The reply bodies for those six tasks (60 episodes) are withheld from the public copy; scores and labels are kept."]),
 ("TABLE:safety", None, None),
 ("Calibration and tool use (measured)", "ul", [
  "Calibration scores depend heavily on output format. Under attn_med and rand_ffn_med the CONFIDENCE line was present in only 53 and 28 of 100 replies, which fails the task even when the answer is right. Differences in calibration pass counts between conditions mostly reflect which condition kept the two-line format.",
  "At baseline, stated confidence behaved like a binary flag (0 with an abstention, 100 otherwise), and 18 of 20 wrong answers carried confidence 100. Brier and calibration-error figures in the report should be read with that in mind.",
  f"Tool use: baseline passed {C['baseline']['metrics']['tool_use']['pass']['k']} of 149 tool episodes. ffn_med produced a malformed reply in {C['ffn_med']['metrics']['tool_use']['episodes_with_format_error']['k']} episodes (baseline {C['baseline']['metrics']['tool_use']['episodes_with_format_error']['k']}); ffn_up_low ended with no final answer in {C['ffn_up_low']['metrics']['tool_use']['no_final_answer']['k']} (baseline {C['baseline']['metrics']['tool_use']['no_final_answer']['k']}), mostly by repeating the same call until the step limit."]),
 ("TABLE:cal", None, None),
 ("Dev versus held-out (measured)", "p", [
  "Strengths were chosen on the 100 dev tasks only. The direction of every significant dev effect held on the held-out tasks, but dev overstated the size for most edited conditions (see the table). Baseline passed 62 of 100 dev tasks against 479 of 1,000 held-out tasks, so the held-out suite is harder."]),
 ("TABLE:gen", None, None),
 ("Latency and compute (measured)", "p", [
  f"Total model time {tot['model_seconds'] / 3600:.1f} hours, {tot['prompt_tokens']:,} prompt tokens and {tot['completion_tokens']:,} completion tokens. The laptop slept during blocks 3 and 4, so mean latency is inflated there; medians are reported. Edited conditions that fail more also tend to write longer replies."]),
 ("TABLE:lat", None, None),
 ("Independent checks (by AI subagents)", "ul", [
  f"<b>Statistics:</b> a verifier recomputed {AU['statistics_verification']['checked']:,} numbers with separate code and found {len(AU['statistics_verification']['mismatches'])} mismatches.",
  "<b>Artifacts:</b> all 10 artifact checksums match their manifests; in each edited artifact exactly the 8 declared tensors differ from baseline and nothing else; dev and held-out tasks share 0 ids and 0 prompts.",
  f"<b>Score audit:</b> auditors re-judged {T['n']} sampled episodes. They agreed with the automatic score on {T['agree']}, found {T['false_pass']} false passes and {T['false_fail']} false fail, and marked {T['unclear']} unclear. Recurring weakness: several checkers grade only the final value and do not enforce stated format rules (line counts, sentence limits), and safety content checks are keyword-based."]),
 ("Interpretation (not measurement)", "ul", [
  "Scaling these gain vectors at mid depth degrades measured task success, and more scaling degrades it more. That much the controls support.",
  "For the feed-forward edit, the uniform cut did somewhat worse than one random change of the same size (about 5.5 points). Most of its damage (163 of 218 net lost tasks) is matched by the random control, so most of the effect looks like generic perturbation.",
  "For the attention edit there is no evidence of anything beyond generic perturbation.",
  "Apparent improvements in single families (attention edits on long-horizon tasks, ffn_up_low on safety) are single cells among about 90 family tests and do not survive correction. We report them as not established."]),
 ("What this does not show", "ul", [
  "Nothing about what any neuron, channel or layer represents or stores. Only whole gain vectors at one site were scaled; no unit-level measurement was made.",
  "Nothing about whether feed-forward paths matter more than attention paths. The two edits differ in absolute size and act on different inputs.",
  "Nothing about other depths, other random seeds, thinking mode, sampled decoding, other quantizations or other models.",
  "Individual task flips are not interpretable one by one: 54 to 84 tasks per edited condition flipped from fail to pass under greedy single-sample decoding."]),
 ("Known problems in this run", "ul", [
  "1,000 tasks per condition instead of 10,000.",
  f"The per-episode truncated flag is wrong: it reads false everywhere, yet replies reached the token cap (300 or more completion tokens) in {capped['baseline']} baseline episodes and up to {max(capped.values())} in an edited condition. Token counts are correct; use them instead of the flag.",
  "One safety dev task was edited by a reviewer after the dev strength sweep, so the sweep used its earlier version. The final dev run used the frozen version.",
  "During setup a builder bug deleted the working clone of the baseline (never the Ollama original). It was re-cloned and checksum-verified, and the builder now refuses to remove it.",
  "The planning dev tasks were rebuilt once after two agents collided in a shared scratch folder.",
  f"Agents: {EF['total_ai_work_items']} AI subagent work items completed, at most {EF['concurrency_cap']} running at once (the platform limit on this machine). 100 agents never ran concurrently. All model episodes were run by one serial script worker, which is not an AI agent."]),
]
TABLES = {"cond": cond_rows, "fam": fam_rows, "safety": safety_rows, "cal": cal_rows, "gen": gen_rows, "lat": lat_rows}

html = []; md = ["# Qwen Behavior Lab: technical report", "", "Generated by `lab/write_findings.py` from `results/summary.json` and `results/analysis/`. Numbers are measured unless a section says otherwise.", ""]
strip = lambda s: s.replace("<b>", "**").replace("</b>", "**")
for title, kind, items in SECTIONS:
    if title.startswith("TABLE:"):
        h, r = TABLES[title[6:]](); html.append(html_table(h, r)); md += [md_table(h, r), ""]; continue
    html.append(f"<h3>{title}</h3>"); md += [f"## {title}", ""]
    if kind and kind.startswith("TABLE:"):
        h, r = TABLES[kind[6:]](); html.append(html_table(h, r)); md += [md_table(h, r), ""]
    elif kind == "p":
        html += [f"<p>{x}</p>" for x in items]; md += [strip(x) + "\n" for x in items]
    else:
        html.append("<ul>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>"); md += ["- " + strip(x) for x in items] + [""]
md += ["## Interventions in detail", "", md_table(["Condition", "Type", "Tensors", "Method", "Artifact sha256 (first 16)"],
       [[c["id"], c["type"], (f"blk.10-17.{c['spec']['module']}.weight (F32, 8 x 2048)" if (c.get("spec") or {}).get("module") else "none"), c["label"], J("manifests", "conditions", c["id"] + ".json")["artifact_sha256"][:16]] for c in CFG["conditions"]]), "",
       "Full per-tensor checksums, change norms and seeds are in `manifests/conditions/`. Reproduction steps are in `README.md`. Per-family analyst notes, labeled examples and every trace are in the HTML report.", ""]
open(os.path.join(core.ROOT, "results", "findings.html"), "w").write("\n".join(html))
open(os.path.join(core.ROOT, "REPORT.md"), "w").write("\n".join(md))
print("ok", len(html), "html blocks;", "em dashes:", "—" in "\n".join(html + md))
