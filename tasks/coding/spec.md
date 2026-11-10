# Family spec: coding (for generator agents)

Model under test: Qwen3 1.7B 4-bit, temperature 0, thinking off. Mode is always `code`; the only
checker is one `code_tests` check. Read `lab/TASKS.md` first; this file adds what the dev pilot showed.

## Task skeleton (use exactly)

    {"local_id": "g<N>-01", "family": "coding", "subtheme": "<your sub-theme label>",
     "difficulty": "easy|medium|hard", "mode": "code", "max_tokens": 320,
     "prompt": "<task text>\nReply with only a ```python code block containing the function, no explanation and no example calls.",
     "checks": [{"type": "code_tests", "tests": "assert f(...) == ...\nassert ..."}],
     "reference": "```python\ndef f(...):\n    ...\n```",
     "negative": "```python\n<plausible near-miss that fails at least one assert>\n```"}

- Always end the prompt with that exact final line on its own line. Always set `max_tokens` to 320.
- Name the function in backticks with its signature (`` `initials(name)` ``), state the return type
  and give 1-3 concrete examples written as `f(args) returns value`, including one edge case.
- The model often replies WITHOUT a fence (bare code). That is fine: the checker falls back to the
  whole reply. Do not add checks about fences.
- Reference solutions must be short (under about 25 lines / 250 tokens), standard library only,
  no input(), no printing, no files, no network, no randomness, no time dependence.

## Tests

- 5-8 asserts: the prompt's examples, then edge cases the prompt explicitly specifies (empty input,
  single element, ties, negatives, duplicates). Never test behaviour the prompt leaves undefined.
- Compute every expected value by running your reference. Tests are run as
  `from solution import *` + tests, 8 s timeout; keep inputs tiny.
- Be lenient on surface form that the prompt does not fix: if the prompt says "list of [a, b] lists"
  do not pass tuples in; if floats are returned use exactly representable values (1.5, 6.0) or
  `abs(x - y) < 1e-9`. Use `is None` / `is True` only when the prompt promises None / a bool.
- The negative must be a realistic wrong answer (off-by-one, missing tie-break, wrong separator,
  the unchanged buggy code), not garbage.

## Pitfalls observed in the pilot

1. Bug-fix prompts that only said "this is wrong, fix it" followed by raw code made the model echo
   the buggy code unchanged (3 of 3 bug-fix tasks, in two runs). What worked (3 of 3 passed):

       The function `range_sum(a, b)` should return the sum of the integers from a to b inclusive (0 when a > b).

       Buggy code:
       ```python
       def range_sum(a, b): ...
       ```

       Symptom: range_sum(1, 4) returns 6 but should return 10.
       Find the bug and write the corrected version of `range_sum`. Your code must differ from the buggy code.
       Reply with only a ```python code block ...

   Always use this layout: one-sentence contract, fenced buggy code, a `Symptom:` line with one
   concrete wrong call, the instruction, the format line. The symptom must be true (run the buggy code).
2. Exact output-format details are a real difficulty lever, not a format bug: asked for 'A.M.L.' with
   a dot after every letter including the last, the model returned 'A.M.L' in all 3 rounds even with two
   examples. Such tasks are legitimate; label them medium or hard, never easy.
3. Stateful sweep algorithms (merge overlapping intervals; compress runs of 3+ consecutive numbers
   into 'a-b') failed with confident, wrong code. These are good hard tasks.
4. Standard idioms pass reliably: grouping into a dict, bracket matching with a stack, distinct
   second-largest, run-length encoding in a given skeleton, Counter + sort with (-count, word) key.
   A task that is a textbook one-liner is at ceiling; add a second requirement to make it medium.
5. With the symptom given, single-line and even two-bug fixes were solved. To make bug-fix tasks
   medium/hard: put the bug in logic rather than a boundary (wrong condition, wrong accumulator
   reset, mutating the input, wrong tie-break), use two interacting bugs, or pick a symptom that
   exposes only one of two bugs (the contract sentence must still state the full behaviour).

## Good task (passed validation, discriminates: baseline fails it)

    prompt: Write a Python function `merge_intervals(intervals)` that takes a list of [start, end] lists
      (in any order, start <= end) and returns a list of merged [start, end] lists sorted by start.
      Intervals that overlap or touch (for example [1, 3] and [3, 5]) are merged into one. Example:
      merge_intervals([[8, 10], [1, 3], [2, 6]]) returns [[1, 6], [8, 10]].
      Reply with only a ```python code block containing the function, no explanation and no example calls.
    tests: the example, [], touching pair, fully nested intervals, two disjoint out of order, one point interval
    negative: same loop but `out[-1][1] = e` instead of max(...)

## Difficulty guidance

Final dev pilot: 8/10 (round 1 was 3/10 before the bug-fix layout was repaired). The baseline is a
little ABOVE the 40-75% target, so skew harder than the dev set: about 25% easy, 35% medium, 40% hard.
- easy: one idea, textbook idiom, one stated edge case (expect the baseline to pass).
- medium: two requirements that interact (grouping + ordering, parsing + validation), or a one-bug
  fix where the bug is in the logic.
- hard: exact output format with separators/thresholds, sweep/state-machine algorithms, tie-break
  rules, two-bug fixes, skeletons where two blanks must agree. Still solvable in under 25 lines.
Never make a task hard by making the statement vague; every tested behaviour must be stated.

## Do not reuse the dev functions

initials, range_sum, invert, rle, merge_sorted, second_largest, is_balanced, merge_intervals,
moving_avg, top_words (and trivially renamed variants).

## Five sub-themes (one per generator; stay inside yours)

1. **Text parsing and formatting from a spec** (`subtheme: "text-format"`). Write a function from a
   prose spec whose input and/or output is a string: parse 'key=value;key=value' records, format
   durations or tables, normalize whitespace/case, validate identifiers, wrap or pad text, caesar-style
   fictional ciphers. Difficulty comes from exact separators, padding and edge cases stated in the prompt.
   No bug-fix or skeleton prompts, and no dict/list restructuring as the main point.
2. **Bug fixing** (`subtheme: "bugfix"`). Every task gives a short contract, fenced buggy code (6-15
   lines), a `Symptom:` line and asks for the corrected function, using the layout in pitfall 1.
   Vary the bug class: off-by-one, wrong comparison, wrong initial value, state not reset in a loop,
   early return, mutable default argument, input mutated, integer vs float division, wrong tie-break.
   Tests must fail on the unchanged buggy code (use it as the negative).
3. **Completing partial implementations** (`subtheme: "complete-partial"`). The prompt gives a
   function with a docstring-style description and 1-3 `...` placeholders (a loop body, a condition,
   a helper) plus the instruction "Keep the given lines and replace the `...` parts"; the reply is the
   whole function. Also allowed: a given helper function that the model must call from a new function
   (include the helper in the prompt and tell the model to include it in the reply). Cover loops,
   recursion, small classes with 2-3 methods, generators. Not plain write-from-scratch tasks.
4. **Collections and data-structure manipulation** (`subtheme: "data-structures"`). Write-from-spec
   functions over dicts, nested lists, sets, tuples and records (lists of dicts): group, join two
   tables on a key, flatten or reshape, transpose/rotate small matrices, deduplicate by key, sort with
   multi-level tie-breaks, diff two dicts, stack/queue simulations. Inputs and outputs are Python
   data structures, not formatted strings; no number theory or search algorithms.
5. **Small algorithms and numeric edge cases** (`subtheme: "algorithms"`). Write-from-spec
   classic small algorithms on numbers and sequences: binary search variants, prime/gcd/base
   conversion, sliding windows, prefix sums, longest run/streak, two-pointer problems, interval
   sweeps other than plain merging, small grid walks, change-making with fictional coins. Emphasize
   stated boundary cases (empty, zero, negative, single element). Outputs are numbers, booleans or
   simple lists, not formatted strings.
