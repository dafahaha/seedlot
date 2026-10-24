# seedlot

**Multi-seed RL result aggregation gate.** Give it per-seed run logs; it computes
n, mean ± sample std, IQR, median and a 95% CI, and fails closed when a claim is
not supported. Hard FAIL (exit 3): a single seed, or two arms whose CIs overlap.
WARN (exit 2): fewer than 3 seeds, zero variance, or duplicate labels/stems —
inspect before claiming stability, but these are not a hard block.

Pure Python standard library. No network, no torch/numpy/scipy, no C build.
Runs on Windows / macOS / Linux with Python 3.10+.

## What problem this solves

RL results are seed-sensitive, but agents and researchers routinely write a
headline mean from one lucky curve or call two overlapping distributions
"better". Reviewers flag this as "only one seed" / "no distribution" repeatedly.
seedlot turns the logs you already have into a distribution summary and blocks
the unsupported wording before it reaches a draft.

It does **not** train anything, does not run a formal hypothesis test, and does
not rescue a weak experiment — it reports what the numbers allow you to say.

## Install

No build, no dependency install.

- **Claude Code (from GitHub, personal marketplace):**

  ```bash
  claude plugin marketplace add dafahaha/seedlot
  claude plugin install seedlot@dafahaha-skills
  ```

  In a session, the same flow is `/plugin marketplace add dafahaha/seedlot`
  followed by `/plugin install seedlot@dafahaha-skills`.

- **Claude Code (local development):** `claude --plugin-dir ./seedlot`.

- **Portable skill (Codex CLI / Cursor / Gemini CLI / Roo Code):** copy
  `skills/seedlot/` into the client's skills directory (`~/.codex/skills/`,
  `.agents/skills/`, ...). Only `name`/`description` frontmatter are required by
  those clients; the extra fields are ignored.

## Usage

Directory mode — one CSV per seed, reward column auto-detected:

```bash
python skills/seedlot/scripts/seedlot.py ./runs --arm-name my-method
```

Two-arm comparison:

```bash
python skills/seedlot/scripts/seedlot.py ./runs/method \
  --compare ./runs/baseline --compare-name baseline \
  --reward-column eval_return --json
```

Single CSV with a seed column, average the last 5 episodes per seed:

```bash
python skills/seedlot/scripts/seedlot.py all_runs.csv \
  --seed-column seed --last-k 5 --output report.md
```

### Input format

- Directory: every `.csv` is one seed; final row of the reward column = seed value.
- Single CSV: `--seed-column` groups rows; `--reward-column` picks the metric.
- Auto-detected reward columns: `reward`, `eval_return`, `return`,
  `episode_return`, `mean_return`, `score`.

### Exit codes

| code | meaning |
|---|---|
| 0 | clean summary, no warnings |
| 2 | warnings (n<3, zero variance, duplicate labels, ...) |
| 3 | hard gate failure (single seed, overlapping CIs) |
| 1 | usage / IO error (missing file, empty directory, unreadable/malformed input, no data) |

## Output

Markdown by default; `--json` emits a structured payload (summary, comparison,
failures, warnings) for CI gating. The Markdown `## gates` section lists each
FAIL/WARN line-level reason.

## Related work

- [rliable](https://github.com/google-research/rliable) (arXiv:2108.13264) is the
  paper-grade benchmark library: stratified bootstrap CIs, IQM, performance
  profiles, probability of improvement, with numpy/scipy dependencies and a
  `(runs × tasks)` matrix input. seedlot does not replace it; it is a zero-install,
  writing-time gate over the per-seed logs you already have, with exit codes for
  CI, and it makes no formal inference.
- Stable-Baselines3 `evaluate_policy` averages evaluation episodes of one trained
  policy; it measures evaluation noise, not the across-training-seed distribution
  this tool summarizes.

## Tests

```bash
python -m pytest tests/ -q
```

49 tests, stdlib only. Manual predicate-mutation spot checks (flipping the
CI-overlap predicate turns the overlap tests red; recorded in CHANGELOG).

## Limits (honest)

- Descriptive statistics only — no formal hypothesis test, bootstrap, or Bayesian
  interval; wide small-n CIs are left wide on purpose. A *non-overlapping* 95% CI
  is a numerical gate, not proof of superiority; *overlapping* CIs are a
  conservative "do not claim superiority" heuristic, not proof the arms are equal.
- t critical values are exact through df=30; beyond that a Cornish-Fisher t
  approximation is used (accurate to <5e-4 vs scipy; it converges to the 1.96
  normal tail as df grows), so the CI is not narrowed by a hard 1.96.
- Trusts the seed labels: it cannot detect that two labeled seeds actually ran
  identical initializations.
- Reads the CSVs you pass into memory; point it at local logs, not a multi-GB dump.
- Does not record environment/library versions; keep a separate manifest.
- Not a paper-writing assistant; it only checks the numbers against the claim.

## License

MIT, © 2026 Daizhi Liao (dafahaha).
