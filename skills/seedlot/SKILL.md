---
name: seedlot
description: Aggregate per-seed reinforcement-learning run logs into an honest distribution summary and gate headline claims. Use when the user has finished one or more RL training runs and wants to report results, compare two algorithms/arms, write a results section, or ask "is this result stable / can I say we beat the baseline". Reads per-seed CSVs, reports n, mean +/- sample std, IQR, median and 95% CI, and fails closed on a single seed or overlapping CIs. Pure stdlib Python, offline, no training.
license: MIT
compatibility: Python 3.10+; standard library only; works on Windows/macOS/Linux; no network access.
---

# seedlot — multi-seed RL aggregation gate

## When to activate

- The user has finished RL runs and is about to write numbers into a report, README, paper draft, or comparison table.
- The user asks whether a result is "stable", "significant", or whether they can claim their method beats a baseline.
- There is a folder of per-seed logs (SB3 `progress.csv`, custom CSVs, or one CSV with a seed column).

Do **not** use this to run training, tune hyperparameters, or perform a formal hypothesis test. It summarizes numbers the user already produced and blocks unsupported wording.

## Input conventions

- One CSV per seed (directory mode): the reward column's final row is that seed's value; use `--last-k K` to average the last K rows instead.
- One CSV with a seed column (`--seed-column seed`): rows group by label; every row of a repeated label feeds that label's last-K mean (no silent overwrite), and a warning names the repeated label. In directory mode, two CSVs sharing the same file stem warns; the later file still wins — rename files so each seed has a distinct stem.
- Reward column auto-detects: `reward`, `eval_return`, `return`, `episode_return`, `mean_return`, `score`; otherwise pass `--reward-column`.
- Rows must be numeric; blank rows are skipped, a non-numeric cell raises a clear error naming the file and seed.

## Steps

1. Locate the per-seed logs. If the user only has one curve, stop and tell them n=1 cannot support a distribution claim before running anything.
2. Run the script (adjust column names to the data):

```bash
python skills/seedlot/scripts/seedlot.py <runs_dir_or.csv> \
  --arm-name my-method \
  [--compare <baseline_dir_or.csv> --compare-name baseline] \
  [--reward-column eval_return] [--seed-column seed] [--last-k 5] \
  [--json] [--output report.md]
```

3. Read the `## gates` section:
   - `FAIL` (exit 3): single seed, or the two arms' 95% CIs overlap — do not write a superiority claim.
   - `WARN` (exit 2): n<3, zero variance, duplicate seed labels, duplicate CSV stems, etc.
   - Clean (exit 0): report n, mean +/- std and the CI; still state environment, scale and n in the text.
   - A df>30 normal-approx CI only adds a note in the report; it does not change the exit code.
4. In a two-arm comparison, pass Cohen's d magnitude alongside the mean difference; a disjoint CI is necessary but not sufficient for a claim.
5. Translate the summary into distribution language ("mean +/- std over n seeds, 95% CI [...]"), never a cherry-picked best curve.

## What the numbers mean (do not overclaim)

- n=1: point only, no CI, no robustness statement.
- n=2: warning; report both raw values, no "stable".
- n>=3: report the distribution; CI uses an exact small-sample t table through df=30; beyond df=30 the normal 1.96 tail is used and flagged as an approximation in the report.
- Overlapping CIs: the samples are consistent with no difference; say "no observed separation at this n".

## Boundaries

- No hypothesis test (no ANOVA/Bootstrap); no Bayesian analysis; does not check environment/library versions (record those separately in a manifest).
- Overlapping 95% CIs are a conservative "superiority not supported" heuristic, not proof the two arms are equivalent.
- Does not validate that the user actually ran independent seeds (identical configs collide) — it trusts the labels given.
- Small-n CIs are wide by design; a wide CI is information, not something to hide.
- Paper-grade benchmark statistics (bootstrap CI, IQM, performance profiles) belong to [rliable](https://github.com/google-research/rliable) (needs numpy/scipy); this tool is a zero-install writing-time gate and does not replace it.

See [references/method-notes.md](references/method-notes.md) for the statistical conventions and cited background.
