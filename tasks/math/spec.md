# Family spec: math (for generator agents)

Mathematical and logical reasoning with one verifiable final answer. Mode `single` only.
Read `lab/TASKS.md` first; this file only adds what the dev pilot on the baseline model showed.

## Prompt and format conventions (these worked in the pilot)

Every prompt = the problem statement, then ONE of these format sentences, verbatim:

- Integer answer:
  `Show at most 5 short lines of working, then end with a final line in exactly this form: 'ANSWER: <number>' (digits only, no units, no LaTeX).`
- Decimal answer (probabilities, averages):
  `Give the answer as a decimal rounded to 2 decimal places. Show at most 5 short lines of working, then end with a final line in exactly this form: 'ANSWER: <decimal>' (for example 'ANSWER: 0.25'; no fractions, no percent sign, no LaTeX).`
- Name / word answer (logic puzzles):
  `Reason in at most 6 short lines, then end with a final line in exactly this form: 'ANSWER: <name>' (one name only).`

Always set `"max_tokens": 320`. No `system` field. Keep prompts under about 600 characters.
Use invented people, places and coins/tokens as currency; nothing real-world sensitive.

## Checker patterns

- Integer: `[{"type":"number","value":126}]`
- Decimal to 2 dp: `[{"type":"number","value":0.42,"tol":0.0051}]`
- Name/word: `[{"type":"exact","value":"Kip"}]` (or `exact_any` if two spellings are truly equivalent)

Do NOT add a regex that requires the `ANSWER:` line on number tasks. The model sometimes ends
with `\boxed{30}` or gets cut off right after `ANSWER:`; the `number` checker then falls back to
the last number in the whole reply, which was the correct answer in every such case observed.

Exact semantics to design around (`lab/core.py`):

- `number` reads the LAST number on the last `ANSWER:` line. So the answer must be a single plain
  number. Never ask for fractions (`3/4` reads as 4), clock times (`13:30` reads as 30), ranges,
  ordered pairs, `x = 2, y = 5`, or anything with a unit containing a digit (`m2`). If a problem has
  two unknowns, ask for one of them or for their sum.
- `exact` compares the normalized text after `ANSWER:` (case-insensitive, outer punctuation
  stripped). `ANSWER: Lena owns the dog` fails, so answers must be one short token and the prompt
  must say "one name only". Use distinct names that are not substrings of each other.
- `reference` = two or three lines of working plus the `ANSWER:` line. `negative` = the most
  tempting WRONG answer (the trap value, an intermediate result, the off-by-one), same shape.

## Pitfalls observed

1. Verbosity and truncation. The model writes LaTeX-heavy step lists and ignores "at most 5
   lines" when the method has many terms. A 3-set inclusion-exclusion count ran out of tokens at
   320 and scored 0 on an intermediate number. Prefer problems whose full working fits in about
   8 short lines; do not rely on the model being brief.
2. Right answer, wrong reasoning. On a 5-runner ordering puzzle the model violated a clue
   ("Kip did not finish first") yet "Who finished third?" was still answered correctly. Asking
   "Who finished second?" exposed the error. Ask for the quantity that changes when the
   hardest clue is ignored, and make the negative that trap answer.
3. Textbook problems are at ceiling. The baseline solved, with correct working: multi-step
   arithmetic, linear equations, two-equation word problems, markup/discount, pipes-and-drain
   work rates, unit conversion, Chinese-remainder with small moduli, C(7,3) with an exclusion,
   C(9,4) increasing digits, two-dice prime-sum probability, a 2-term linear recurrence to a7.
4. Output is not perfectly reproducible. Re-running an unchanged file changed wording and token
   counts of some replies, so avoid tasks that only pass or fail by a hair (for example answers
   that depend on exactly fitting the token budget).
5. Compute every expected answer with python (brute force where possible, e.g. enumerate all
   permutations to prove a logic puzzle has exactly one solution). Never trust mental arithmetic.

## Example of a good task

```json
{"local_id":"g5-03","family":"math","subtheme":"logic-ordering","difficulty":"hard","mode":"single",
 "prompt":"Five runners (Kip, Oro, Vale, Juno, Sam) finished a race with no ties. Vale finished immediately after Oro. Kip finished before Oro, but Kip did not finish first. Juno finished last. Who finished second? Reason in at most 6 short lines, then end with a final line in exactly this form: 'ANSWER: <name>' (one name only).",
 "max_tokens":320,
 "checks":[{"type":"exact","value":"Kip"}],
 "reference":"Juno 5th. Kip is not 1st and is before Oro, Vale is right after Oro: Sam 1, Kip 2, Oro 3, Vale 4.\nANSWER: Kip",
 "negative":"Order Kip, Sam, Oro, Vale, Juno.\nANSWER: Sam"}
```

(This is dev-10; do not reuse it, its numbers or its names.)

## Difficulty guidance

Final dev pilot on the baseline: 8/10 (both failures labelled hard; 3/3 easy, 3/3 medium, 2/4 hard).
That is slightly above the 40-75% target, so generators must skew HARDER than the dev set:

- easy (about 2 in 10): 2-3 step problem with one small twist. Expect the baseline to pass.
- medium (about 4 in 10): 4-5 steps AND a trap: a distractor number, a backward question
  ("what was it before"), a remainder/rounding decision, a unit change mid-problem, a condition
  that removes some cases. A standard one-formula textbook problem is easy, not medium.
- hard (about 4 in 10): needs holding 4+ constraints at once, a case split, working backward
  through several operations, or a count where the naive formula over- or under-counts. It must
  still be solvable in about 8 short lines by a careful solver, and have one unambiguous answer.

Never make a task hard through ambiguity, huge arithmetic (keep numbers under about 10,000),
obscure terminology or long reading. Each task must differ from the others in content AND in
reasoning; do not write templates with swapped numbers, and do not reuse dev scenarios.

## Sub-themes (one generator each; stay inside your own)

1. **Arithmetic, rates and units.** Multi-step word problems on quantities, money in coins,
   percentages (markup, discount, percent change), ratios and proportions, speed/distance/time,
   work rates, unit conversions with the conversion factor stated in the prompt, averages.
   Integer or 2-dp decimal answers. No equations to solve for an unknown as the main skill
   (that is theme 2), no divisibility or counting arguments.
2. **Algebra.** Solving for an unknown: linear equations, systems of two linear equations,
   word problems that must be translated into equations (ages, mixtures, ticket sales),
   quadratics with integer roots (ask for the larger root or the sum), inequalities (ask for the
   largest or smallest integer that satisfies them), evaluating or simplifying expressions and
   simple functions. Single number answers only.
3. **Number theory and sequences.** Divisibility, primes and factor counts, gcd/lcm (including
   disguised as scheduling or tiling), remainders and modular arithmetic, digit sums and digit
   puzzles, base conversion to or from base 10, arithmetic/geometric sequences, recurrences,
   finding the next or n-th term, sums of series. Integer answers.
4. **Combinatorics and probability.** Counting arrangements, selections, paths and codes with
   restrictions; inclusion-exclusion with at most two sets; pigeonhole; probabilities with dice,
   coins, marbles and cards drawn with or without replacement; expected value. Counts are
   integers; probabilities and expectations are decimals rounded to 2 dp (tol 0.0051).
5. **Logic and deduction.** Pure deduction with no computation beyond counting: ordering and
   seating puzzles, who-owns-what assignment grids (3-5 entities), truth-teller/liar puzzles,
   syllogisms and set membership, "which statement must be true" with lettered options
   (answer one letter), elimination from clues. Answer is one name, one word, one letter or a
   small integer (a position). Prove uniqueness by brute force before writing the task.
