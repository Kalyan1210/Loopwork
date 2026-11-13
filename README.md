# Qwen Behavior Lab

A controlled experiment on a local `qwen3:1.7b` model: ten conditions (baseline, direct weight
edits, matched random controls, no-op and rollback controls), each run on the same 1,000 held-out
tasks from ten task families. 10,000 scored episodes in total, plus 1,000 dev episodes.

The original Ollama model file was never written to. All edits were made on copy-on-write clones.

## Where to look

| What | Where |
|---|---|
| HTML report (filters, charts, traces, swarm replay) | `report/standalone.html` (single file), or `report/index.html` served over HTTP |
| Technical report | `REPORT.md` |
| Video walkthrough (motion design, 85 s, silent) | `report/walkthrough.mp4`, editable source in `video/` |
| Earlier screenshot walkthrough of the report and swarm replay | `report/walkthrough_screens.mp4` |
| Machine-readable results, one JSON line per episode | `results/episodes/<condition>.jsonl`, `results/dev_final/<condition>.jsonl` |
| Statistics | `results/summary.json` |
| Agent audits, analyses and verification | `results/analysis/*.json` |
| Task definitions | `tasks/suite_eval.jsonl` (1,000 held-out), `tasks/suite_dev.jsonl` (100 dev) |
| Manifests and checksums | `manifests/` |
| Agent and run event log | `swarm/events.jsonl` |

To open the multi-file report and the live dashboard:

```bash
.venv/bin/python lab/dashboard_server.py 8790
```

Then visit `http://localhost:8790/report/index.html` (report) or `http://localhost:8790` (dashboard).

## Shortfalls against the original brief, stated plainly

- **Episodes:** the brief asked for 10,000 tasks per condition. This machine (Apple M3, 8 GB) runs
  about 0.4 episodes per second, so the run is 1,000 tasks per condition: 10,000 episodes in total.
- **Agents:** the platform runs at most 6 AI subagents at a time on this machine. More than 100
  named AI work items were completed in bounded batches. 100 agents never ran at once.
- **Model runs were not done by AI agents.** One serial script worker (`run-worker-1`) ran all
  model episodes. The event log marks every actor as `ai_subagent`, `coordinator` or `script_worker`.
- **Latency:** the laptop slept during blocks 3 and 4 of the held-out run, so wall-clock latency
  for those blocks is inflated. Scores are unaffected (greedy decoding, fixed seed, zero errors).

## Reproduce

Requirements: macOS on Apple silicon (APFS for copy-on-write clones), Ollama with `qwen3:1.7b`
pulled, llama.cpp `llama-server` on the PATH, Python 3.13.

```bash
python3 -m venv .venv && .venv/bin/pip install gguf==0.19.0 numpy
```

```bash
.venv/bin/python lab/inventory.py
```

```bash
.venv/bin/python lab/interventions.py build all
```

```bash
.venv/bin/python lab/interventions.py verify
```

```bash
caffeinate -i .venv/bin/python lab/runner.py --suite tasks/suite_eval.jsonl --out results/episodes --blocks 10
```

```bash
.venv/bin/python lab/runner.py --suite tasks/suite_dev.jsonl --out results/dev_final --blocks 2 --quiet-events
```

```bash
.venv/bin/python lab/analyze.py && .venv/bin/python lab/report_data.py
```

The held-out run takes about 6.5 hours with the machine awake and on power. The runner is
resumable: rerun the same command and it skips finished episodes. Decoding is greedy with a fixed
seed, so the same artifacts on the same llama.cpp build should give the same replies; a different
build or GPU backend may differ slightly.

`manifests/conditions/<id>.json` lists, for every condition, the edited tensors, the method, the
magnitude, the seed, per-tensor checksums before and after, and the artifact checksum. Compare
your rebuilt artifacts against those.

## Layout

- `lab/core.py`: inference client, sandboxed tools, checkers, scoring
- `lab/interventions.py`: builds and verifies condition artifacts
- `lab/runner.py`: randomized, blocked, resumable run
- `lab/analyze.py`, `lab/report_data.py`: statistics and report data
- `lab/dashboard_server.py`, `lab/dashboard.html`: live dashboard and replay
- `swarm/`: event log, workflow scripts, per-agent evidence
