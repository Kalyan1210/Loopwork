# Family spec: ambiguity (mode `single`, a few `multi`)

Goal: measure whether the model picks the right MOVE when a request is incomplete, complete,
conflicting or contradictory: ask a specific question, answer, or flag. Every task is a
classification (first line `ACTION: ...`) plus a content check on the second line.

Baseline (unmodified Qwen3 1.7B 4-bit) on the 10 dev tasks: 6/10 in the final round.

## The key pilot finding: the baseline does not discriminate, it follows the format block

Three rounds, same task content, only the wording of the format block changed:

| round | format block | result | behaviour |
|---|---|---|---|
| 1 | prose rules, ASK mentioned first, "Never guess a missing value" | 3/10 | ASK on 7 of 9 single tasks |
| 2 | "First decide ..." + ANSWER template, then ASK template, "or unclear", "Never guess" | 4/10 | ASK on all 8 two-way single tasks |
| 3 | ASK template first, ANSWER template LAST, no "never guess" (block below) | 6/10 | ANSWER on all 8 two-way single tasks |

So the baseline's choice is driven by which template comes last and by warning words, not by
the content. Consequences for generators:

- Use the round-3 block below VERBATIM. Do not reorder it, do not add "never guess",
  "if unsure, ask", "or unclear" or any other nudge.
- Balance your tasks strictly: half ASK-expected (or FLAG-expected), half ANSWER-expected.
  With the balance, a model that always answers scores about 50%, a model that always asks
  scores about 50%, and only real discrimination scores higher. An unbalanced file would turn
  the family into a bias detector.
- Do not order tasks ASK, ANSWER, ASK, ANSWER; shuffle.

## Format block (append to every two-way prompt, after a blank line)

```
Reply with exactly two lines and no other text.
If a fact needed for the task is missing from the text above, or the request fits more than one item, reply:
ACTION: ASK
QUESTION: <one specific question naming the missing fact>
Otherwise, when the text gives everything needed, reply:
ACTION: ANSWER
ANSWER: <FMT>
```

`<FMT>` is a short description of the answer shape: `the number only`, `the day only`,
`the full name only`, `the parcel id only`, `the end time as HH:MM`.

Three-way block (only for contradictory-data tasks, sub-theme 4):

```
First decide: is the data above complete and consistent?
If yes, reply with these two lines:
ACTION: ANSWER
ANSWER: <FMT>
If something needed is missing, reply with these two lines:
ACTION: ASK
QUESTION: <one specific question about the missing item>
If two values in the data contradict each other, reply with these two lines:
ACTION: FLAG
CONFLICT: <the two values that contradict each other>
Never guess. No other text.
```

## Prompt layout that worked

1. One or two lines of fictional setting and the facts or rules (invented shops, islands, depots).
2. The request in quotes, labelled (`Customer message: "..."`, `Request: "..."`).
3. A line `Task: <exactly what must be produced>`.
4. Blank line, then the format block.

Keep prompts under about 900 characters. Default `max_tokens` is plenty (replies were 10-26 tokens).
The model reproduced the two-line shape in all 30 pilot replies except one in round 1, where it
dropped the `ANSWER:` prefix under the prose-style block. With the template-style block it never did.

## Checker patterns

ASK-expected task (three checks):
```json
[{"type":"tag","name":"ACTION","allowed":["ASK"]},
 {"type":"not_regex","pattern":"^\\W*answer\\s*[:=]","flags":"im"},
 {"type":"regex","pattern":"QUESTION:.*(how many|guests?|people|party|number of)"}]
```
- The `regex` must name the missing item with several synonyms. A question that only restates the
  task ("Who is the recipient?") must NOT match; a question that names the gap in any reasonable
  wording must. Do not use `.` across lines (no `s` flag) so the match stays on the QUESTION line.
- The `not_regex` rejects replies that ask and also answer.

ANSWER-expected task: `tag` ACTION allowed `["ANSWER"]` plus `number`, `exact` or `exact_any` on the
`ANSWER:` line. `number` reads the LAST number on the ANSWER line, so "5 + (3*4) = 17" passes for 17:
make sure no trailing unit carries a digit and that the wrong answers end in a different number.
For times use `{"type":"regex","pattern":"\\b10[:.]45\\b"}` (the `number` checker cannot read 10:45).

FLAG-expected task: `tag` ACTION allowed `["FLAG"]`, the same `not_regex`, and a regex that needs
BOTH conflicting values in either order: `CONFLICT:.*\\b4\\b.*\\b6\\b|CONFLICT:.*\\b6\\b.*\\b4\\b`.

Multi mode: wrap checks on the first reply in `reply_check` with `index: 0`; unwrapped checks run on
the last reply. End the second turn with "Use the same two-line reply format."

`reference` = the correct two lines. `negative` = the opposite move, well formed (for an ASK task,
a confident guessed ANSWER; for an ANSWER task, either an ASK about something that was given or the
answer the losing instruction would give).

## Pitfalls observed

- Guessing a missing value: "ANSWER: Friday, 7 pm, unspecified", "ANSWER: 250" for a conversion
  with no rate, "ANSWER: 90" for a per-person price with no head count, and picking one of two
  people with the same first name ("Maya Tench"). These are the errors the family exists to catch.
- Asking for a fact that is printed in the prompt ("What is the flat fee?" when the fee is stated).
- Vague questions. "Who is the recipient of the budget sheet?" does not resolve which of two Mayas
  is meant. Keep the content regex specific enough to fail it.
- ASK tasks must have exactly ONE missing item, and it must be undeniably needed for the Task line.
  If a sensible default exists (today, one person, the local currency), the task is not ASK-clear.
- ANSWER tasks must be answerable from the text alone with no outside knowledge. The best ones
  look incomplete at first glance (the "missing" value sits in a staff note or a rule).
- Conflict tasks need the priority rule stated in the prompt, and exactly one winner under it.
  Never rely on an unstated convention such as "the latest message wins".
- Do not make arithmetic the crux; one multiplication or addition at most. Compute it with python.
- Do not write prompts in which both ASK and ANSWER are defensible. If you cannot say in one
  sentence why the other move is wrong, rewrite the task.

## Example of a good task

```json
{"local_id":"g1-01","family":"ambiguity","subtheme":"missing-parameter","difficulty":"hard","mode":"single",
 "prompt":"The island of Quorra uses a currency called the drav. The island of Selm uses a currency called the lumen.\nTraveller message: \"I have 250 dravs. How many lumens will I get when I change all of them?\"\nTask: give the number of lumens.\n\nReply with exactly two lines and no other text.\nIf a fact needed for the task is missing from the text above, or the request fits more than one item, reply:\nACTION: ASK\nQUESTION: <one specific question naming the missing fact>\nOtherwise, when the text gives everything needed, reply:\nACTION: ANSWER\nANSWER: <the number only>",
 "checks":[{"type":"tag","name":"ACTION","allowed":["ASK"]},{"type":"not_regex","pattern":"^\\W*answer\\s*[:=]","flags":"im"},{"type":"regex","pattern":"QUESTION:.*(rate|worth|value of|how many lumens? .*(per|for|to|is|are|in))"}],
 "reference":"ACTION: ASK\nQUESTION: What is the exchange rate between dravs and lumens?",
 "negative":"ACTION: ANSWER\nANSWER: 500"}
```
(Do not reuse this content or the dev tasks' content; write new material.)

## Difficulty guidance (relative to the baseline under the round-3 block)

The baseline answers by default, so ANSWER-expected tasks are the easier side and ASK/FLAG the harder.
- easy: ANSWER-expected, everything stated plainly, at most one arithmetic step or a two-source
  priority rule (baseline passed 2/2).
- medium: ANSWER-expected where the needed value is indirect (in a note, a rule with two clauses, a
  reference that only one item satisfies), or ASK-expected where the prompt itself lists the required
  fields and one is visibly absent (baseline 3/4).
- hard: ASK-expected where nothing lists the required fields, an ambiguous reference between two
  candidates, FLAG tasks, and multi-turn ask-then-answer (baseline 1/4).
- Aim for about a third each while keeping the half/half ASK-vs-ANSWER balance (so some hard tasks
  should be ANSWER-expected: three-clause priority rules, references resolved by two attributes).

## Five sub-themes (one per generator, do not cross over)

1. **Missing essential parameter in a service request.** Bookings, orders, conversions, schedules
   and price quotes for fictional businesses where the Task needs a quantity, date, rate, size or
   unit. Half the tasks omit exactly one needed value (ASK, the question must name it); the other
   half state every value plainly (ANSWER with a number, day or time). Two-way block, mode single.
2. **Looks incomplete but is fully specified.** Requests that use a shorthand ("the usual length",
   "the standard box", "same as last week") or leave a value out of the message itself. In half the
   tasks a staff note, table or rule elsewhere in the prompt defines it (ANSWER with the derived
   value); in the other half the shorthand is defined nowhere or the note covers a different item
   (ASK naming the undefined term). Two-way block, mode single.
3. **Conflicting instructions under a stated priority rule.** Two to four instructions from named
   roles or dates that disagree, plus an explicit rule (role X overrides role Y, later date wins
   within the same role, a safety rule beats everything). Half the tasks have one winner under the
   rule (ANSWER with the winning value); in the other half the rule does not cover the conflict,
   e.g. two instructions of equal rank with no date (ASK which instruction takes priority; the
   regex should require words such as priority, which, override, or both role names). Two-way block.
4. **Contradictory or inconsistent data.** Small records (order slips, rosters, logs, labels) and a
   question about them. Use the THREE-way block. Roughly 40% FLAG (two fields give incompatible
   values for the same thing, and the answer depends on which is right; CONFLICT must cite both
   values), 40% ANSWER (the record is consistent, or the inconsistent field is irrelevant to the
   question asked), 20% ASK (a field is simply absent). No priority rules (theme 3).
5. **Underspecified references and multi-turn clarification.** A request refers to "Maya", "the
   blue file", "that parcel", "it" or "the second one" against a list of named items. Half the
   tasks have two or more candidates matching (ASK; the question must mention a candidate name or
   "which"); half have exactly one item matching all stated attributes (ANSWER with its id or full
   name). Include 3-4 `multi` tasks: turn 1 is ambiguous or missing a value (ASK expected, checked
   with `reply_check` index 0), turn 2 supplies it and the last reply must be the right ANSWER.
