# Qwen Behavior Lab motion walkthrough: review notes

85 s, 1920x1080, 30 fps, nine scenes in `compositions/s1.html` to `s9.html`. Silent.

## Creative calls

- Look borrowed from the reference the user gave (the Astra motion piece): light grey stage, near-black ink,
  one sans face at regular weight, pill and chip shapes, blur-in type, a word that rolls through options,
  a black closing card. No assets, font, logo or copy from the reference are used.
- Story built: "one question, typed". A bar types "what if we turn [one dial] down?", the chip becomes the
  model (28 blocks, eight scaled to x0.70), then 1,000 tasks x 10 conditions, the no-op control, the results
  chart, the matched random control, the baseline safety decisions, the agent checks, the claim and its limit.
- Storylines not built: (1) a single task followed through all ten conditions as one reply card that
  rewrites itself; (2) the event log replayed as a timeline the camera flies along.
- Every scene hands off through the same ink dot, which stretches in a different direction each time.
- Colour carries meaning only: green baseline, blue edit, orange control.

## Numbers on screen and where they come from

All from `results/summary.json`, `results/score_audit.json` and `swarm/engine_facts.json`:
479, 486, 434, 417, 344, 261 passed of 1,000; -21.8 points (272 regressed, 54 improved); +0.7 points;
261 vs 316 (5.5 points); 417 vs 388 (interval -0.4 to +6.4); 1 / 22 / 7 decisions on 30 disallowed requests;
108 agent work items, six at a time; 2,074 statistics recomputed with 0 mismatches; 453 of 480 audited scores agree.

## Checked

- `hyperframes check`: no errors. Frames looked at for every scene, every seam and at phone width.

## Not checked, and kept warnings

- No sound. No music source was available in this session, so the film is silent on purpose (`film_silent`).
- `contrast_aa_failure` at 42.5 s: the five dimmed bars while the camera pushes in on one. Intended.
- Nobody watched it at full speed; pacing was judged from sampled frames.

## Weakest shot

Scene 7 (safety decisions): the tiles are abstract. With more time, show one real fictional request and its
first-line decision before the grid.
