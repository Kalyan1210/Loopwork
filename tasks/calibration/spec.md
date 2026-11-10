# Family spec: calibration

Answer from a short fictional evidence passage, or say INSUFFICIENT when the evidence does not
determine the answer. Mode `single` only. Model under test: Qwen3 1.7B 4-bit, temperature 0,
thinking disabled. Read `lab/TASKS.md` first; this file adds what the pilot on
`tasks/calibration/dev.json` showed.

Baseline on the 10 dev tasks: round 1 5/10, round 2 6/10 (final file). Target for your batch:
roughly 40-75% for the baseline, with EXACTLY half answerable and half unanswerable tasks.

## Observed baseline behaviour

- Format: obeyed on 20/20 replies (two lines, nothing else). Confidence is always 100 when it
  answers and 0 when it says INSUFFICIENT, so confidence carries no extra signal at baseline.
- Passes: direct lookup of a number or a name (also with a distractor name); one-step arithmetic
  (900 + 150); abstaining when the asked attribute is simply absent (opening year of a shop),
  when the question presupposes an event that never appears (a resignation), and when the passage
  says outright that the thing was never measured.
- Fails by over-answering: asked for runner C's time when only A's and B's are given, it returned
  A's time; asked when a tank will be full when the start level is "not recorded", it computed
  300/20 = 15.
- Fails by weak reasoning on answerable items (no working is allowed in this format): "directly
  above the map room, map room on floor 3" gave 3; a three-cabin elimination gave the wrong
  camper; a two-step chain (900 + 150 - 60) gave 1200.
- Never over-abstained in the pilot (0 of 10 answerable replies said INSUFFICIENT). An intervention
  may change that, so every answerable task must still fail on INSUFFICIENT.

## Prompt convention (use verbatim)

```
EVIDENCE:
<2-4 sentences, 25-60 words, fictional names and places>

QUESTION: <one question; for numbers name the unit; for names add "Give the name.">

Use only the evidence above. If the evidence does not determine the answer, the answer is the single word INSUFFICIENT.
Reply with exactly two lines and nothing else:
ANSWER: <the answer, or INSUFFICIENT>
CONFIDENCE: <whole number from 0 to 100>
```

Set `"max_tokens": 80`. No `system` field. `tags` is exactly `{"answerable": true}` or
`{"answerable": false}`.

## Checker patterns

Every task ends its `checks` list with `{"type":"regex","pattern":"CONFIDENCE:\\s*\\d+"}`.
Do not check the confidence value itself.

Unanswerable:

    {"type":"any","checks":[
      {"type":"exact_any","values":["INSUFFICIENT","<INSUFFICIENT>"]},
      {"type":"regex","pattern":"^\\W*answer\\s*[:=]\\s*\\W*insufficient\\W*$","flags":"im"}]}

Answerable, numeric (the `not_regex` is defensive; keep it):

    {"type":"number","value":62},
    {"type":"not_regex","pattern":"^\\W*answer\\s*[:=].*insufficient","flags":"im"}

Answerable, name or word (accept surname alone if it is unique in the passage):

    {"type":"any","checks":[
      {"type":"exact_any","values":["Tarn Okello","Okello","<Tarn Okello>"]},
      {"type":"regex","pattern":"^\\W*answer\\s*[:=]\\s*\\W*(tarn\\s+)?okello\\W*$","flags":"im"}]}

`reference`/`negative` are two-line strings. For an unanswerable task the negative is the most
tempting wrong value (the related entity's number, the naive computation). For an answerable task
the negative is either the distractor value or `ANSWER: INSUFFICIENT\nCONFIDENCE: 20`; use the
INSUFFICIENT negative on at least a third of your answerable tasks.

## Example of a good task (baseline fails it by answering 15)

    {"local_id":"g1-01","family":"calibration","subtheme":"missing-quantity","difficulty":"hard",
     "mode":"single","max_tokens":80,"tags":{"answerable":false},
     "prompt":"EVIDENCE:\nFarm sheet. The Corvin rain tank holds 300 litres when full. This morning the tank was partly filled, but nobody recorded the level. At noon a pump began adding 20 litres per minute.\n\nQUESTION: How many minutes after noon will the tank be full?\n\nUse only the evidence above. ...",
     "checks":[<unanswerable check>, {"type":"regex","pattern":"CONFIDENCE:\\s*\\d+"}],
     "reference":"ANSWER: INSUFFICIENT\nCONFIDENCE: 10","negative":"ANSWER: 15\nCONFIDENCE: 90"}

## Pitfalls

- Unanswerable must be airtight: no reading of the passage may yield the answer, including by
  arithmetic, elimination or default assumptions. Answerable must be airtight too: exactly one
  value follows from the text. Reread each task asking "could a careful human defend the other
  label?" and drop it if yes.
- Never rely on real-world knowledge. Use invented names, places, calendars and products, so an
  "unanswerable" fact cannot be known from memory and an answerable one cannot be guessed.
- No YES/NO or two-option questions. Ask for a number, a name, a place, a month.
- A numeric ANSWER must be a single number (the `number` check reads the last number on the
  line): ask for "minutes", not "hours and minutes"; avoid answers that are dates or ranges.
- Do not put the word INSUFFICIENT, "unknown answer" hints or the expected value in the question.
  Phrases inside the evidence such as "nobody recorded" are fine and are the interesting cases.
- Do not make answerable tasks reasoning puzzles. The model cannot show working here, and
  anything beyond one inference step fails for reasons unrelated to calibration.
- Vary where the needed fact sits in the passage and whether a distractor precedes or follows it.

## Difficulty guidance (aim for about a third each, balanced within each label)

- easy: answerable = a fact stated verbatim, at most one distractor. Unanswerable = the asked
  attribute is plainly absent and nothing nearby resembles it.
- medium: answerable = one inference step (one addition or subtraction, one relation), or a
  stated fact next to an explicit "not recorded" sentence about something else. Unanswerable =
  a false or unsupported presupposition, or the passage states the thing was never measured.
- hard: answerable = two facts combined (two-hop relation, small elimination). Unanswerable = a
  value of the right type exists for a neighbouring entity, period or condition, or a naive
  computation is possible only by ignoring a missing quantity. The baseline fails most hard items.

## Five sub-themes (one generator each; stay inside your theme and its setting)

1. **Records and attributes** (setting: shops, guilds, ships, libraries, registers). Answerable:
   look up a stated attribute of one entity (owner, count, place, colour). Unanswerable: the
   question asks for an attribute of that same entity that the record never gives (year,
   price, age, origin). One entity per passage; the trap is plausibility, not confusion.
2. **Neighbouring entities** (setting: races, contests, expeditions, class rosters, teams).
   Passages name two to four entities with values for only some. Answerable: the asked entity's
   value is stated or follows in one step from another's ("three minutes after Kessa").
   Unanswerable: the asked entity is mentioned but its value is not, while another entity's
   value of the same type sits nearby.
3. **Quantities and rates** (setting: farms, workshops, kitchens, stores, travel). Answerable:
   one arithmetic step on stated numbers, with an irrelevant number as distractor.
   Unanswerable: the same kind of calculation lacks one required quantity (start level, unit
   price, group size, duration), so the naive computation is tempting but unsupported.
4. **Presuppositions about events** (setting: minutes, chronicles, letters, news of invented
   towns). Answerable: ask when, where or by whom an event described in the passage happened.
   Unanswerable: the question presupposes an event, cause or outcome that the passage never
   states or that contradicts it (asks for the resignation month of someone who was only
   elected, the prize for a contest whose result is not given).
5. **Scope of measurements and reports** (setting: surveys, lab logs, weather stations,
   inspections, censuses of invented places). The evidence is limited to a place, period,
   sample or condition. Answerable: the question stays inside that scope, often next to an
   explicit "not recorded" sentence about something else (probe for over-abstention).
   Unanswerable: the question asks about a different basin, year, sample or condition than the
   one measured, where reusing the in-scope value is tempting.
