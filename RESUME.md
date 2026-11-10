# Qwen Behavior Lab: paused state (2026-11-10)

Paused on user request. Nothing is running: the agent workflow, the dev sweep, all `llama-server`
processes and the dashboard server were stopped. No held-out evaluation run has started, so there
are **no experiment results yet**.

## What exists

| piece | state |
|---|---|
| Baseline | `qwen3:1.7b` Ollama blob untouched, sha256 `3d0b7905...6ab6` re-verified at pause. `artifacts/` (clones, git-ignored) can be rebuilt with `lab/interventions.py`. |
| Inventory | `manifests/baseline.json` |
| Harness | `lab/core.py` (inference, sandbox tools, checkers), `runner.py`, `interventions.py`, `analyze.py`, `report_data.py`, `validate_tasks.py`, `build_suite.py`, dashboard (`dashboard_server.py`, `dashboard.html`) |
| Dev tasks | 10 families x 10, all valid, piloted on baseline by the designers |
| Held-out tasks | 9 families x 105 generated and valid (`tasks/<family>/gen_1..5.json`). **longhorizon has none yet.** |
| Review | **Not done for any family.** Only `review-constraints-a/b` had started. `tasks/suite_eval.jsonl` is a provisional 900-task merge of unreviewed files; rebuild it after review. |
| Audits | safety review x2 and leakage audit not started |
| Dev sweep | `results/dev_tuning/`: 345 of 800 episodes (7 candidate strengths + baseline, block 0 of 2 mostly done). Resumable. |
| Event log | `swarm/events.jsonl`, 60 subagents seen, 54 reported done, 6 stopped by the pause (marked as written by the coordinator) |

## To resume

1. Start the pilot server and dashboard:
   `llama-server -m artifacts/baseline.gguf --port 8791 -c 8192 -np 1 -ngl 99 --seed 0 --no-webui`
   and `.venv/bin/python lab/dashboard_server.py 8790`.
   If `artifacts/baseline.gguf` is missing, `lab/interventions.py build baseline` re-clones it.
2. Finish the task suite. In the same Claude session, relaunch the workflow with
   `resumeFromRunId: wf_3de3450e-f3e` (finished agents are cached). In a new session, run a new
   workflow for only the missing items: `gen-longhorizon-1..5`, all 20 reviewers
   (`review-<family>-a` on gen 1-3, `-b` on gen 4-5), `safety-review-1`, `safety-review-2`,
   `leakage-audit`. Prompts are in the saved workflow script (copy in `swarm/workflow_task_suite.js`).
3. `lab/build_suite.py` to freeze `suite_eval.jsonl` (1,000 tasks) and `suite_dev.jsonl`.
4. Finish the dev sweep (pilot server must be stopped first, memory is tight):
   `.venv/bin/python lab/runner.py --suite tasks/suite_dev.jsonl --out results/dev_tuning --blocks 2 --config manifests/tuning_config.json --quiet-events`
5. Choose low and medium strengths from the dev sweep only, then write the final
   `manifests/intervention_config.json`. Planned conditions: baseline, no-op, ffn_norm low/medium,
   attn_norm low/medium, one amplification, matched random control for each medium edit
   (`"matched_control_for"` key), rollback. The current file is a pipeline-test config.
6. Held-out run: `caffeinate -i .venv/bin/python lab/runner.py --suite tasks/suite_eval.jsonl --out results/episodes --blocks 10`
   (about 3.5 s per episode measured on dev, so roughly 10 hours for 10,000 episodes).
7. `lab/analyze.py`, post-run agent workflow (score audit, family analysts, verification, HTML
   report, video), `lab/report_data.py`, final push.

## Known facts and decisions

- Workflow engine cap on this machine: 6 concurrent subagents (min(16, cores - 2)).
- Parallel llama.cpp slots gave no speedup (GPU-bound), so there is one serial run worker.
- 10,000 episodes per condition is not feasible here; plan is 1,000 tasks x ~10 conditions.
- Only unquantized F32 norm-gain tensors are edited (exact, in place, on a clone).
- A builder bug once deleted the working clone `artifacts/baseline.gguf` (never the Ollama
  original). It was re-cloned, checksum verified, and the builder now refuses to remove it.
