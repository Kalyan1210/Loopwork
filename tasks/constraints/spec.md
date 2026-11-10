# Family spec: constraints (mode `single`)

Goal: measure whether the model follows precise, machine-checkable output constraints.
The reply itself is the answer: do NOT use an `ANSWER:` line in this family.
Baseline (unmodified Qwen3 1.7B 4-bit) on the 10 dev tasks: 5/10. Keep that mix: about a
third of your tasks should be ones the baseline plausibly passes, a third coin-flips, a third hard.

## Prompt conventions that worked in the pilot

- Put the data first, then the rules, then "Reply with ONLY ... No other text." The model obeyed
  "ONLY" every time: no preambles, no code fences, no commentary in any of the 10 replies.
- State each rule as a literal shape: `numbered like "1. Name"`, `in the format name=price`,
  `join them with " | " (space, vertical bar, space)`. A one-line shape example on DIFFERENT data
  (e.g. `for the list a, b: BEGIN b, a END`) helps and does not leak the answer.
- Strict JSON: name every key in quotes with its type, then "No other keys and no extra text."
  The model emits pretty-printed multi-line JSON without a fence; `json` strict accepts that.
- Use invented names (towns, ships, shops) and short prompts (under ~500 characters).
- Default `max_tokens` (200) is plenty; replies were 4-41 tokens.

## Checker patterns

- Case-sensitive rules: `regex` with `"flags": ""` (an absent `flags` means case-INSENSITIVE).
  `exact` and `json.equals` on strings are case-insensitive, so they cannot verify a case rule.
  For case inside JSON, add a second check: `{"type":"regex","flags":"","pattern":"\"key\"\\s*:\\s*\"value\""}`.
- Whole-reply shape: anchor with `^\s*...\s*$` and use `"flags":"s"` (or `"is"`) for multi-line
  replies. Between lines write `\s*\n\s*`, not `\n`: the model ends list lines with two trailing
  spaces (markdown line breaks).
- Line rules: `line_count` plus `lines_regex` (lines are stripped before matching; every non-empty
  line must match, so an intro line fails, which is what you want).
- Exact word count N: `min_words` N and `max_words` N and `line_count` 1 (words are whitespace
  separated tokens; punctuation attached to a word does not add a word).
- Forbidden words: `not_regex` with `\b(rain\w*|wet\w*)\b` so inflections are caught but innocent
  substrings are not (`contains_none` is a substring test: "wet" would hit "sweet"). Always pair
  with a required word and a `min_words`, otherwise an empty or off-topic reply passes.
- Strict JSON: `{"type":"json","strict":true,"is":"object","keys":[...],"equals":{...}}`.
  `keys` is an exact key-set match; lists in `equals` compare exactly (case-sensitive).
- The `negative` should be a near miss that breaks exactly one constraint (wrong case, one extra
  key, two items swapped, an intro line), not a blank or nonsense reply.

## Pitfalls observed (all were genuine model errors, checks were correct)

- Silent content edits during a transform: "lantern" came back as "LANTERNS". Keep checks exact.
- A rule applied to most but not all lines: 2 of 3 lines ended with "!", one with ".".
- Length limits ignored in free writing: 25 words where at most 20 was allowed, and the reply
  drifted off topic to satisfy the forbidden-word list.
- Filter + sort together: wrong membership and wrong order at once (returned 2 of 3 items, unsorted).
- Derived fields in JSON: wrong initials ("OD" for Odessa Pike) and wrong longest surname.
- Picking one of three options under a format rule gave the wrong option ("GRANITE" as the fruit):
  avoid making a knowledge question the crux; the constraint should be the crux.
- Free-form generation with one tight rule (exactly 7 words) can pass, so "exact count" alone is
  not automatically hard. Combine two or three rules for hard tasks.
- Do not require things a checker cannot see (rhyme, tone, "be polite", syllables).
- Avoid constraints with several defensible readings (does a hyphenated word count as one word?
  alphabetical order with mixed case?). Use plain lowercase or capitalized single words.

## Example of a good task

```json
{"local_id":"g1-01","family":"constraints","subtheme":"filter-sort-format","difficulty":"hard","mode":"single",
 "prompt":"Price list (fictional shop):\nkettle 18\nspoon 4\nteapot 31\nnapkin 2\nstrainer 12\ncoaster 9\n\nList ONLY the items that cost more than 10, sorted from most expensive to cheapest. One item per line in the format name=price (lowercase name, no spaces). No other text.",
 "checks":[{"type":"line_count","value":3},{"type":"regex","flags":"s","pattern":"^\\s*teapot=31\\s*\\n\\s*kettle=18\\s*\\n\\s*strainer=12\\s*$"}],
 "reference":"teapot=31\nkettle=18\nstrainer=12","negative":"kettle=18\nteapot=31\nstrainer=12"}
```
(Do not reuse this content or the dev tasks' content; write new material.)

## Difficulty guidance (relative to the baseline)

- easy: one constraint, answer copied or trivially derived (extract 3 fields to JSON, sort 5
  distinct words, one case rule on a given word). Baseline passed 3/3.
- medium: two constraints, or one transform plus one format rule (uppercase + separator, reverse +
  wrapper words, per-line prefix AND suffix, forbidden + required word + length cap). Baseline 1/4.
- hard: three or more interacting constraints or a computed/derived value inside a strict format
  (filter + sort + format, JSON with counted and derived fields, exact counts). Baseline 1/3.
- Aim for a third each. Compute every expected answer with python.

## Five sub-themes (one per generator, do not cross over)

1. **Strict JSON output.** The reply must be ONLY a JSON object or array with an exact key set and
   exact values taken or derived from a short fictional text (extraction, type rules such as number
   vs string, nested object, list of fixed length, key order irrelevant). Check with `json` strict
   + `keys` + `equals`/`list_len`. No line-based or prose tasks.
2. **Ordered and filtered lists.** Plain-text lists, one item per line in a stated line format:
   sort (alphabetical, numeric, by length), reverse, filter by a rule, top-k, renumber. Check with
   `line_count` plus one anchored whole-reply `regex`. No JSON and no free writing.
3. **Counts and length limits in free writing.** The model writes original text about a fictional
   subject under numeric rules: exactly N words, exactly N lines, at most N words per line, exactly
   N sentences each on its own line, a required word. Check with `min_words`/`max_words`,
   `line_count`, `lines_regex`. The content is free; only the counts and required tokens are checked.
4. **Lexical and case rules.** Forbidden words, required words, all-uppercase or all-lowercase,
   capitalize each word, required first word or last word, required prefix and suffix on every
   line, no digits, no commas. Check with case-sensitive `regex`/`not_regex`/`lines_regex`
   (`"flags":""`), always paired with a positive content check and `min_words`.
5. **Transform-and-format of given strings.** The model rewrites supplied items deterministically
   into one exact output: change case, join with a stated separator, wrap in fixed BEGIN/END style
   markers, key=value or `name (n)` templates, date or code reformatting such as 2031-04-07 to
   07/04/2031, abbreviations and initials. One correct answer exists; check with one anchored
   case-sensitive `regex`. No sorting or filtering (theme 2) and no JSON (theme 1).
