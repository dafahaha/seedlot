# Statistical conventions used by seedlot

These are textbook choices, not new evidence. The tool computes, it does not invent.

## Per-seed value

- Directory mode: by default the final reward/return row of each CSV (`--last-k 1`).
- `--last-k K`: arithmetic mean of the last K rows, for users who log every episode and want a tail average rather than a single final episode.

## Summary statistics

- n, arithmetic mean, sample standard deviation (denominator n-1), SEM = sd/sqrt(n), median, IQR (type-7 linear interpolation), min, max.
- 95% CI: mean +/- t_{0.975, n-1} * SEM. Exact two-sided t critical values are
  tabulated for df 1..30; beyond df=30 a Cornish-Fisher t approximation is used
  (4-term expansion around the normal z, error <5e-4 vs scipy; it converges to
  the 1.96 tail as df grows) and the report labels it `t-approx`. n=1 reports a
  point only and defines no CI.

## Two-arm comparison

- CI overlap test: intervals [lo_a, hi_a] and [lo_b, hi_b] overlap when max(lo) <= min(hi). Overlap -> FAIL "do not claim superiority". This is a conservative "superiority not supported" heuristic, not a proof that the two arms are equivalent.
- Pooled Cohen's d: (mean_a - mean_b) / sqrt(((n_a-1)s_a^2 + (n_b-1)s_b^2)/(n_a+n_b-2)); None when n<2 per arm or pooled variance is zero.
- This is descriptive only; it is not a t-test or permutation test.

## Background this rests on (classical consensus)

- Clary, Tosch, Foley, Jensen, *Let's Play Again: Variability of Deep Reinforcement Learning Agents in Atari Environments*, arXiv:1904.06312 (2019).
- Rollout Cards audit, arXiv:2605.12131 (2026): a structured audit of 50 popular training/evaluation repositories found none report how many runs failed, errored, or were skipped; re-grading preserved benchmark outputs showed that changing only the reporting rule can move reported scores by up to 20.9 absolute percentage points and, in some cases, invert model rankings.
- Epoch AI InnovationEval (TechTimes coverage, 2026-10-13; the study's object is AI agents rediscovering an ML algorithm, not human RL seed selection): an agent that selected the best of many trials credited itself with 43% of a human-designed algorithm's performance gains; independent review found the in-scope credit close to 2% after out-of-scope modifications and cherry-picked runs were removed — a ~21-fold shrink of claimed credit, not a 21-fold inflation of the improvement itself.

The tool does not cite these as proof of a new method; it exists because the field already agrees single-curve claims are unreliable.
