# Family spec: synthesis (multi-document research synthesis)

Read `lab/TASKS.md` first. This file adds the conventions that worked in the baseline pilot
(Qwen3 1.7B 4-bit, final dev pass rate 7/10). `tasks/synthesis/dev.json` holds 10 worked examples.

## What a synthesis task is
A bundle of 3-5 short FICTIONAL documents plus one question whose answer is a short checkable
fact that cannot be read from any single document. Every task must need 2+ documents. Test it:
delete each document in turn; if the question is still answerable from one document, rewrite it.

## Prompt conventions (use exactly these)
- First line: `Read the three documents, then answer.` (adjust the count word).
- One document per line: `[Doc A] <source type>, <title>: <1-3 sentences>`. Letters A-E. Give each
  a source type (invoice, site log, council minutes, memo, leaflet...) and one irrelevant detail.
- Blank line, then `Question: ...` as ONE question.
- Output format, one of:
  1. Answer line (default). End the prompt with:
     `Reply with one short line of working, then end with a final line in exactly this form:`
     newline `ANSWER: <number>` (or `<branch name>`, `<B, C or D>`, `<letter> and <letter>`).
  2. Strict JSON for two-part answers: `Reply with only a JSON object like {"day": <number>, "room": "<room name>"} and nothing else.`
- Invented proper nouns only (Marlow, Brannock, Quillon...). No real people, firms, places or events.
  Years 2030+ or clearly historical-fictional. Numbers small: 2-4 digit integers, no decimals
  unless the task is about them. Prompt under 1500 characters. `max_tokens` default (200).
- Tool mode (at most 1 task in 5): put 4-5 docs in `env.docs` with short lowercase ids without dots,
  tools `["search","read_doc","calc"]`, a plain question naming the entities, and the instruction
  "give the <thing> as a number in your final answer". Do not re-explain the tool protocol.

## Checker patterns
- Numeric answer: `{"type":"number","value":N}` (reads the last number on the ANSWER line, so the
  answer slot must contain ONE number: ask for "day number", never a full date like "25 March 2031").
- Name answer: `exact_any` with the bare name and natural longer forms, e.g.
  `["Ossby","Ossby Branch","Ossby Branch Library"]`. The model often appends the noun ("Passen office").
- Document letter: `exact_any` `["C","Doc C","[Doc C]"]`.
- Pair of letters: a regex anchored on the ANSWER line that accepts both orders and "A and D" / "A, D" /
  "Doc A and Doc D" and rejects three letters (copy the dev-05 pattern, flags `im`).
- Two-part answer: strict `json` with `keys` and `equals`; for a name value that may carry a suffix,
  put the number in `equals` and add a separate `regex` on the name field (see dev-10).
- Tool mode: `number` on the final plus `{"type":"tool_called","tool":"read_doc","min":1,"ok_only":true}`.
- `negative` must be the most tempting wrong answer (the single-document answer, the uncorrected
  figure, the pre-update value), not an arbitrary one.
- Compute every expected value with python before writing it down.

## Pitfalls seen in the pilot
- With an ANSWER line the model writes working and gets sums right (3 addends, one multiplication
  were fine). With JSON-only output it has no room to work: a "largest change between two censuses"
  task failed because it picked the largest town. JSON-only tasks are therefore harder; use that
  deliberately, not by accident.
- Chained adjustments across documents (plan date, then "+9 days", then "+2 more days") failed: the
  model answered with the first document's date. Good medium/hard lever.
- Implicit contradictions (a "centenary in 2011" versus "completed in 1904") among 5 documents
  failed, with long rambling working and no ANSWER line. Explicit same-form contradictions
  (1904 vs 1911) passed easily. Do not hint which documents agree.
- 3-hop lookups (person -> team -> site -> office), even with an overriding later memo, PASSED. A
  lookup chain alone is not hard; add arithmetic or an implicit step to make it hard.
- Explicit overrides ("Later notices override earlier ones") passed. Unstated precedence is ambiguous: always
  state the precedence rule or date the documents and say which wins.
- Avoid ties, "approximately", percentages needing rounding, and questions with two defensible answers.
- Do not put the answer value verbatim in a document unless a wrong value is equally prominent.

## Good example (medium, passed; negative is the uncorrected total)
```json
{"local_id":"g1-01","family":"synthesis","subtheme":"aggregation with correction","difficulty":"medium","mode":"single",
 "prompt":"Read the three documents, then answer.\n\n[Doc A] Harvest tally, Yarrowfield Co-op: North orchard 120 kg of pears, East orchard 85 kg of pears, South orchard 140 kg of pears.\n[Doc B] Correction slip: The East orchard figure in the harvest tally was misread. The correct East orchard weight is 95 kg.\n[Doc C] Buyer agreement: The Yarrowfield Co-op is paid 4 florins for every kilogram of pears.\n\nQuestion: Using the corrected figures, how many florins is the co-op paid for the whole pear harvest?\n\nReply with one short line of working, then end with a final line in exactly this form:\nANSWER: <number>",
 "checks":[{"type":"number","value":1420}],
 "reference":"120 + 95 + 140 = 355 kg, and 355 x 4 = 1420.\nANSWER: 1420",
 "negative":"120 + 85 + 140 = 345 kg, and 345 x 4 = 1380.\nANSWER: 1380"}
```

## Difficulty guidance (aim for a third each)
- easy: 3 documents, one comparison or one sum of 3 figures, or one explicit override. ANSWER line.
- medium: 3-4 documents, two reasoning steps (sum then match a claim, correct then multiply,
  3-hop lookup, tool-mode lookup plus subtraction).
- hard: 4-5 documents, an implicit step (derived date, unit or period conversion, per-entity
  differences then argmax), chained adjustments, or JSON-only output for a computed answer.
Expect the baseline to pass nearly all easy, most medium and few hard tasks.

## Five sub-themes (one generator each; stay inside yours)
1. **Cross-document comparison and ranking.** Each document reports the same kind of measure for a
   different entity (or period). Ask which entity is highest/lowest/second, or by how much one
   exceeds another, including per-entity change between two dated documents. Answers are a name, a
   number, or a {name, number} JSON. No totals across entities and no corrections.
2. **Aggregation and derived totals.** Figures scattered over documents must be summed, netted
   (budget minus spends), or multiplied by a rate given in another document, sometimes after
   filtering by a criterion stated in a separate document (only items of one category count).
   Answers are single numbers. No "which is biggest" questions.
3. **Timeline and update reconciliation.** Documents are dated notices, logs or memos where later
   ones shift, extend or override earlier ones (delays in days, moved rooms, revised deadlines,
   durations between events in different documents). Ask for the final day number, the elapsed
   days, or the final {day, place}. Always state or make evident which document takes precedence.
4. **Claim verification and source attribution.** One document is a record (ledger, roster,
   log) and the others make claims about it, or a claim is stated in the question. Ask which single
   document's claim agrees with the record, which document supports or refutes the stated claim, or
   whether a claim is SUPPORTED or REFUTED by the bundle (with the letter of the deciding document).
   Answers are a document letter or a fixed label.
5. **Contradiction detection and entity linking.** Either (a) 4-5 documents describe one subject and
   exactly two conflict on one fact (explicitly for easy, via a derived value for hard); ask for
   the pair of letters or the conflicting fact; or (b) relational chains where a fact about an
   entity must be followed through 2-3 documents (person -> team -> project -> site) to a name.
   Answers are letter pairs or names; no arithmetic totals.
