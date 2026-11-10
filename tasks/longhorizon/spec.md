# Family spec: longhorizon

State tracking across several steps. Mode `multi` (4-6 scripted user turns, the last one asks
about or ends in the resulting state) and mode `tool` (5-8 dependent steps over kv / files).
Model under test: Qwen3 1.7B 4-bit, temperature 0, thinking disabled. Read `lab/TASKS.md` first;
this file only adds what three pilot rounds on `tasks/longhorizon/dev.json` taught us.

Baseline on the 10 dev tasks: round 1 1/10, round 2 4/10, round 3 4/10 (final 0.40).
The model is far weaker than you expect. Aim low, and never rely on silent tracking for easy tasks.

**Core rule: the final answer must be wrong if any single earlier update is lost.** Write the
`negative` as the answer you get by dropping exactly one update (usually the correction, the
reversal, or the last movement), and make sure no two different mistakes cancel out.

## What the baseline can and cannot do (observed)

Passes:
- Latest-value overwrite with a distractor and a correction, when it may acknowledge each turn
  freely (it restates the new setting each turn and reads it back at the end).
- Echoed counter with small round numbers (20, -5, +10, -3) replying `STOCK: <number>` each turn.
- Object moves between three containers with free acknowledgement, including one bulk move
  ("everything in the green drawer goes into the blue drawer").
- Tool mode: following a 4-entry pointer chain with `kv_get` and summing with `calc`.

Fails:
- Silent tracking ("Reply with only the word NOTED until I ask"): at the final question it
  recomputes from memory and drops the late update (a reversal, a swap, all removals from a queue).
- Echoed counter with bare numbers and no label, less round numbers: 24, 15, then 24 again.
- Running total with a correction: 26, corrected by -3, gave 22 (off by one), then propagated.
- Queue with a swap: produced a duplicated name (`Rahel, Mirek, Dov, Mirek`).
- Tool mode, arithmetic between a read and a write: wrote the value back unchanged, or added a
  "sold" amount instead of subtracting, or applied only one item of two.
- Tool mode: computed the right sum with `calc` and then finished without the required `kv_set`.
- Tool mode: skipped `read_file` and invented values (`north = 100`).
- Tool mode: emits several JSON objects in one reply. Only the first is executed, so the model
  then repeats itself and burns steps. It also copies the `(3+4)*2` example from the system prompt.

## Prompt and format conventions that worked

Multi mode. Pick ONE reply policy and state it in turn 1:
1. **Labelled echo** (easiest): `After each of my messages, reply with only one line in the form
   STOCK: <number> giving the current number of lanterns.` The last turn is just one more update,
   and the check runs on the last reply. Always use a label (`STOCK:`, `TOTAL:`, `QUEUE:`); bare
   numbers failed. Set `"max_tokens": 60`.
2. **Free acknowledgement** (easy to medium): `Acknowledge each update in a few words.` Then a
   final question turn with an explicit format. Set `"max_tokens": 80`.
3. **Silent** (hard only): `Reply with only the word NOTED until I ask a question.` Final turn:
   `Keep any working under 40 words, then end with a final line in exactly this form: ANSWER: <number>`.
   Set `"max_tokens": 260`.

Final answer formats and checks:
- Number: `Reply with one line in exactly this form: ANSWER: <number>` with
  `{"type":"number","value":N}`. The same check works on an echoed `STOCK: 22` line (it reads the
  last number of the reply), so the last echoed line must contain one number only.
- Two or three named slots: `Reply with only a JSON object with exactly the keys "key" and "coin";
  each value is a drawer colour.` with a NON-strict
  `{"type":"json","is":"object","keys":[...],"equals":{...}}` (`equals` ignores case).
- Ordered names: `reply with only one line in the form QUEUE: followed by the names from front to
  back, separated by commas` with an anchored regex such as
  `^\W*(queue\W+)?rahel\W+mirek\W+dov\W+suri\W*$` (flags `i`). Do NOT ask for a JSON array: the
  model answered `{"names": [...]}` and a strict array check rejected a well-formed reply. Use
  plain ASCII names (it wrote `Surí` once).
- Never ask a yes/no or two-option final question.

Tool mode:
- Do not re-explain the JSON protocol. Describe the job in plain sentences, name every key and
  file exactly, and end with `Final answer: <what>, just the number.`
- Always set `"max_steps": 8`. The reference should need at most 6 tool calls plus the final,
  because the model wastes steps on repeated calls.
- Include `calc` in `tools` and say "use the calc tool" whenever arithmetic is needed.
- Check the END STATE, not only the answer: `env_equals` on every key that must change, one
  `env_equals` on a key that must NOT change (add an untouched distractor key or file), plus
  `number` on the final. Numeric `env_equals` accepts `"46"` stored as a string.
- Use `tool_called` with `args_contains` and `"ok_only": true` to prove a required read happened.
- For files: no dots in checked file names (`orders`, `done`, not `orders.txt`). Ask for file
  content that is "just the number" and check with `env_equals`, since `env_contains "43"` would
  also accept `143`. Use `env_absent` for required deletions.
- Do not add `no_tool_errors` or tight `max_tool_calls`: they fail correct but clumsy runs.

## Checker rules

- Compute every expected state by simulating the updates in python (asserts), never by hand.
- The answer must differ from every intermediate state and from the start value, so a stale
  answer never passes by accident. Also avoid answers equal to a number that appears in a distractor.
- A `number` check reads the LAST number in the ANSWER line (or the whole reply): one number only.
- `reference` for multi mode is one reply per turn, following the reply policy you chose.
- Keep total prompt + env under 900 characters.

## Example of a good task (passes baseline, medium)

```json
{"local_id":"g2-01","family":"longhorizon","subtheme":"object-locations","difficulty":"medium","mode":"multi","max_tokens":80,
 "turns":["Track where things are in a fictional workshop. There are three drawers: red, blue and green. The key is in the red drawer, the coin is in the blue drawer and the ring is in the green drawer. Acknowledge each update in a few words.",
  "I move the key from the red drawer to the green drawer.",
  "I move the coin to the red drawer.",
  "I move everything that is in the green drawer into the blue drawer.",
  "Which drawer is the key in now, and which drawer is the coin in now? Reply with only a JSON object with exactly the keys \"key\" and \"coin\"; each value is a drawer colour."],
 "checks":[{"type":"json","is":"object","keys":["key","coin"],"equals":{"key":"blue","coin":"red"}}],
 "reference":["Noted.","Noted.","Noted.","Noted.","{\"key\": \"blue\", \"coin\": \"red\"}"],
 "negative":["Noted.","Noted.","Noted.","Noted.","{\"key\": \"green\", \"coin\": \"red\"}"]}
```

## Difficulty guidance (relative to this model)

- easy (about 40%): 4 turns or 4-5 tool steps; labelled echo or free acknowledgement; small round
  numbers; overwrites or single moves; tool tasks that only read and combine (reads then one
  `calc`). The baseline should pass most of these.
- medium (about 35%): 5-6 turns; one correction or one distractor turn; a bulk move; tool tasks
  with ONE write after a computed value, or a read from a file followed by an update. Baseline
  passes some.
- hard (about 25%): silent tracking; reversals ("undo the payment from B to C"); swaps inside
  an ordered list; two or more accounts; tool tasks with arithmetic between read and write on
  two keys, or write + report file + delete. Baseline fails nearly all; keep them few and correct.
- Make a task hard through the number and kind of updates, never through ambiguity or long text.

The dev set landed at 0.40, the low end of the target. Skew your file slightly EASIER than the
dev set: aim for about half of your tasks solvable by the baseline.

## The five sub-themes (one per generator; do not cross into another's)

1. **Numeric tallies and ledgers (multi).** One or more quantities changed by additions and
   subtractions across 4-6 turns: stock counts, scores, fuel, coin balances. Include corrections
   ("the Round 2 score was 6, not 9"), reversals, and unrelated-number distractor turns; the hard
   end is two or three accounts paying each other. The final answer is always a single number.
   No object locations, no ordered lists, no tool mode.

2. **Entity and attribute state (multi).** Categorical state rather than arithmetic: which
   container holds which object, who currently owns or is assigned what, device or room settings
   that get overwritten, statuses that flip (open/closed, on/off, colour). Updates are moves,
   bulk moves, swaps of contents, overwrites and corrections. The final answer is a name, a
   colour, or a small JSON object of two or three named slots. No sums, no ordering questions.

3. **Ordered lists and sets (multi).** Sequences and memberships: queues, playlists, bookshelf
   order, relay line-ups, guest lists, to-do lists. Updates are join at back or front, leave,
   serve the front, swap two neighbours, move to a position, remove by name. The final answer is
   the ordered names on a labelled comma-separated line, or who is at position k, or how many
   remain. No balances, no containers, no tool mode.

4. **KV inventory and ledger updates (tool).** The kv store holds counts or balances; the prompt
   itself states the movements (sales, deliveries, transfers between two keys, fees). The model
   must read current values, compute with `calc`, write back with `kv_set`, and report one number.
   Easy tasks only read and consolidate into one new key; hard tasks update two or three keys
   that depend on each other. Always include an untouched distractor key. Tools: `kv_get`,
   `kv_set`, `kv_list`, `kv_delete`, `calc` only; no files and no docs.

5. **Chained lookups and file workflows (tool).** Each step's result decides the next step:
   pointer chains through kv entries or files ("each entry names the next key"), a file of
   instructions or movements that must be read before the kv store or another file is updated,
   then a result written to a named file and a processed file deleted. The final answer is a
   number or a name found only at the end of the chain. Every task must involve at least one
   `read_file` or a lookup chain of 3+ hops; do not write plain kv arithmetic tasks whose
   movements are stated in the prompt (that is sub-theme 4).
