# Family spec: planning

Multi-step planning with ONE checkable answer. Mode `single` only. Model under test: Qwen3 1.7B
4-bit, temperature 0, thinking disabled. Read `lab/TASKS.md` first; this file only adds what the
pilot on `tasks/planning/dev.json` taught us.

Baseline on the 10 dev tasks: round 1 0/10, round 2 3/10, round 3 4/10 (5/10 once a checker that
rejected a correct inline `ANSWER:` was fixed). The model is much weaker than you expect: aim low.

## What the baseline model can and cannot do (observed)

Passes: a 4-step chain stated as "X comes before Y"; adding three durations with one forced wait;
picking the minimum of three routes that are already enumerated; spotting which of three rules a
3-step plan breaks; a 3-person assignment with two direct constraints.

Fails: anything needing more than about two inference steps. Critical path over 6 tasks (reported
one path, not the longest); bin packing where the weight/capacity lower bound is not achievable;
timetable with a transfer buffer (took the last bus); shortest path when routes are NOT enumerated
(invented "total minus longest road"); 4x4 assignment; choosing a pair under a budget when it must
reply with JSON only; counting "the third job" in an order it had just derived correctly.

## Prompt and format conventions that worked

1. Number answers. End the prompt with exactly:
   `Keep any working under 60 words. Then end with a final line in exactly this form: ANSWER: <number>`
   Check with `{"type":"number","value":N}`. The model sometimes writes `ANSWER: <5>`; `number` copes.
2. Word or clock answers. End with:
   `Keep any working under 60 words. Then end with a final line: ANSWER: followed by just the <thing>.`
   (for times: `... in exactly this form: ANSWER: HH:MM`). Check with an `any` of an `exact_any`
   and an anchored regex, because the model sometimes puts `ANSWER: x` at the end of a prose line
   instead of on its own line, and `exact` then compares the whole reply:
   `{"type":"any","checks":[{"type":"exact_any","values":["Pell","<Pell>"]},{"type":"regex","pattern":"answer\\s*[:=]\\s*\\W*pell\\W*$","flags":"im"}]}`
   For times list variants: `["10:40","10:40 am","10:40am","<10:40>"]`.
3. Whole plan as JSON, no working. End with:
   `Reply with only a JSON array of the N step names, for example ["a","b"]. No other text.`
   Check with `{"type":"json","strict":true,"is":"array","value":[...]}`. The model obeys the
   format perfectly but cannot reason silently, so use JSON-only replies for EASY tasks only.
4. JSON object after working. Ask it to list the options one per line in plain text, then
   `end with a final line that is only a JSON object with exactly the keys ...`. Check with a
   NON-strict json check (`"is":"object","keys":[...],"equals":{...}`). The working lines must not
   contain `{` or `[`, since the checker takes the first JSON value in the reply.
5. Set `"max_tokens": 300` on every task that allows working (default 200 truncated a reply before
   its ANSWER line in round 1). Keep prompts under about 900 characters.
6. Use words for step names in JSON answers and give all names in lowercase or as proper names
   exactly as they must appear. `json` `value` comparison is case-sensitive; `equals` is not.

## Checker rules

- The answer must be unique. Prove it with a few lines of python (brute force over permutations,
  subsets or routes) before writing the task; do not trust mental arithmetic.
- `negative` must be the most tempting wrong answer (sum of all durations instead of critical
  path, last departure instead of latest feasible one, capacity lower bound, cheapest pair that
  breaks the constraint), not a random one.
- Never use YES/NO or two-option answers (50% by chance). Ask "which rule number", "which step
  is k-th", "how many minutes", "what total cost".
- Do not check with `contains_all` on names that also appear in the working.
- A `number` check reads the LAST number on the ANSWER line, so the ANSWER line must hold one
  number only: ask for minutes, not "1 h 35 min"; ask for a count, not "3 of 5".

## Pitfalls seen

- Angle brackets in the format hint are copied literally (`ANSWER: <5>`). Harmless for `number`,
  fatal for `exact` unless you list the bracketed variant.
- Inline `ANSWER:` at the end of a sentence (see convention 2).
- JSON-only prompts on tasks needing inference: the model emits a confident wrong plan.
- Real-world priors override rules: in a pottery task it put "dry" last despite the rule. Useful
  for hard tasks, unfair for easy ones; make easy rules agree with common sense or use neutral names.
- Problems where the obvious heuristic is right are solved by accident; problems where it is wrong
  are always failed. Mix both so the suite has signal in both directions.

## Example of a good task (passes baseline, easy)

```json
{"local_id":"g1-01","family":"planning","subtheme":"time-window-scheduling","difficulty":"easy","mode":"single","max_tokens":300,
 "prompt":"A mechanic starts work at 09:00 and does three jobs in this fixed order, with no breaks unless forced to wait:\n1. Oil change: 30 minutes.\n2. Brake check: 45 minutes. The brake parts arrive at 10:00, so this job cannot start before 10:00.\n3. Tyre check: 15 minutes.\nAt what time does the mechanic finish the third job? Keep any working under 60 words. Then end with a final line in exactly this form: ANSWER: HH:MM",
 "checks":[{"type":"exact_any","values":["11:00","11:00 am","11:00am","<11:00>"]}],
 "reference":"Oil 09:00-09:30, wait, brakes 10:00-10:45, tyres 10:45-11:00.\nANSWER: 11:00",
 "negative":"30+45+15 = 90 minutes after 09:00.\nANSWER: 10:30"}
```

## Difficulty guidance (relative to this model)

- easy (about 40% of your tasks): one or two inference steps, at most 4 entities, options already
  laid out. The baseline should pass most of these.
- medium (about 35%): three steps, or 5 entities, or one trap (a wait, a constraint that removes
  the cheapest option, counting a position in a derived order). Baseline passes some.
- hard (about 25%): 6-7 entities, critical path, tie-break rules, transfers with buffers, packing
  where the lower bound fails. Baseline fails nearly all; keep them few but correct.
  Never make a task hard through ambiguity or long text; only through reasoning depth.

Target for your own file: roughly half the tasks solvable by the baseline.

## The five sub-themes (one per generator; do not cross into another's)

1. **Dependency ordering.** A set of 4-7 named steps with "X before Y" / "X needs Y"
   prerequisites that admit exactly one order (or one order under a stated tie-break such as
   "alphabetically first among ready jobs"). Ask for the full order as a strict JSON array (easy
   only), or which step is k-th / last / immediately before step S. No durations, clock times,
   costs or people-to-slot assignment.

2. **Clock and duration scheduling.** Jobs with durations placed on a timeline: fixed-order
   sequences with forced waits or breaks, time windows that determine the only feasible order,
   deadlines worked backwards ("latest start"), and parallel work where the answer is the minimum
   total time (longest dependency chain). Answers are a clock time `HH:MM` or a number of minutes.
   No travel legs or timetables, no money.

3. **Assignment and capacity allocation.** Matching people to shifts/rooms/tasks under
   can/cannot constraints with exactly one valid assignment (ask who gets a named slot, or the
   full strict-JSON mapping for easy cases), and capacity problems: minimum number of trips,
   boxes, vans or tables given indivisible items and a capacity. No clock arithmetic, no prices.

4. **Routes and itineraries.** Fictional places joined by roads or services: shortest total
   distance or time among a few routes, required visiting order with a fixed start/end, timetable
   legs with transfer buffers ("latest departure that still arrives by T", "earliest arrival"),
   and number of stops or changes on the best route. Answers are km, minutes, a clock time or a
   place name. For easy tasks enumerate the candidate routes explicitly. No budgets.

5. **Budget plans and plan verification.** Choosing items or options under a spending limit or a
   second constraint (the only affordable combination, the cheapest valid combination, money left
   after a required plan, how many units a budget allows after fixed costs), and auditing a
   proposed plan against numbered rules ("exactly one rule is broken: which number?", "which step
   is the first to break a rule?", "by how many coins does the plan exceed the budget?"). Answers
   are a number, a rule or step number, or a JSON object produced after plain-text working.
