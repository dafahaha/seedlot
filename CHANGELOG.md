# Changelog — seedlot

v1.6.0 — 2026-10-23

## Round-8 independent clean review (fresh reviewer, cold reading)
- Removed the unreachable `n==0` hard-failure branch in `gate_arm`: an empty
  sample is a usage/IO error (exit 1) by contract — `collect()` rejects empty
  dirs/no data rows and `summarize([])` raises, so n==0 never reached it.
- Fully blank rows remain silently skipped in both modes (standard CSV
  behavior); a WARN would fire on every trailing blank line, so this is
  intentional and documented.
- Suite: 52 tests.

v1.5.0 — 2026-10-23

## Round-7 independent clean review (fresh reviewer, cold reading)
- A data row carrying a reward but an empty seed label is now rejected (it used
  to be silently skipped, shrinking n); a fully blank separator row is still
  skipped.
- A short/ragged row missing the reward cell now raises a clean ValueError
  (the direct `row[col]` index could otherwise throw an uncaught KeyError).
- Suite: 52 tests (2 added).

v1.4.0 — 2026-10-23

## Round-6 independent clean review (fresh reviewer, cold reading)
- P2-4 (fixed): the seed column is now resolved exact-then-case-insensitive,
  matching the reward-column behavior (`--seed-column SEED` still finds a
  `seed` header) via `_resolve_seed_column`.
- P2-3 (partial): `csv.Error` is now included in the CLI catch so a malformed
  CSV is a clean exit-1 error (UnicodeDecodeError was already a ValueError).
- New test: case-insensitive seed column. Suite: 49 -> 50.
- Kept as intentional, test-pinned behavior: the duplicate-label warning in
  long-table mode (it tells the user a label spans multiple rows feeding the
  last-K mean) and skipping blank-label rows.

v1.3.0 — 2026-10-23

## Round-5 independent technical review (fresh reviewer, cold reading)
- P1-1 (fixed): argparse usage errors (missing positional, invalid type) exited
  2, colliding with the "warnings" exit code; a custom parser now exits 1 for
  usage errors (--help still exits 0).
- P1-2 (fixed): df>30 used a hard 1.96 normal tail, narrowing the CI and risking
  a false DISJOINT in the overlap gate; replaced with a 4-term Cornish-Fisher t
  approximation (error <5e-4 vs scipy; df=31 -> 2.0395, df=100 -> 1.9840).
  ci_method label is now `t-approx` (was `normal-approx`).
- P2-1 (fixed): reward-column auto-detect is now case-insensitive.
- P2-2 (fixed): broadened the CLI catch to OSError (PermissionError, etc.).
- P2-3 (fixed): `--output` write is inside the try (clean exit 1 on bad path).
- P2-4 (fixed): a missing seed cell (ragged row) raises instead of being
  aggregated as a literal "None" label.
- New tests: usage-error exit 1, conservative t>1.96, case-insensitive column,
  missing seed cell. Suite: 45 -> 49.

v1.0.0 — 2026-10-22

## v1 (baseline)
- Directory-of-CSVs and single-CSV seed-column loading; n/mean/std/SEM/CI/median/IQR/min/max;
  single-seed failure, n<3 warning, CI-overlap comparison gate; Markdown report; CLI exit codes.
- 24 tests green.

## v2 (dirty-input robustness) — quality issue: a malformed cell crashed mid-run with a
traceback that did not name the file/seed.
- Non-numeric reward cell raises `ValueError` naming file and seed; blank rows skipped;
  duplicate seed labels warn (all matching rows feed the last-K mean);
  `collect()` returns `(values, warnings)`.
- New tests: non-numeric location, blank rows, duplicate-label warning.

## v3 (tail averaging) — quality issue: final-episode-only is noisy when logging every
episode, and users had no supported way to average the tail.
- `--last-k K` averages the last K rows per seed (clamps to available length); K<1 rejected.
- New tests: tail mean, clamp when K exceeds length.

## v4 (machine-readable gate) — quality issue: Markdown cannot be consumed by CI scripts.
- `--json` emits summary/comparison/failures/warnings payload; comparison includes
  ci_overlap and Cohen's d; `--output` works for both formats.
- New tests: JSON payload shape, JSON comparison overlap.

## v5 (spec compliance + manual mutation spot check)
- Frontmatter limited to spec fields (name/description/license/compatibility); manifest
  follows official plugin.json rules; README documents install/limits honestly.
- Manual predicate-mutation spot check: inverted `intervals_overlap` -> 3 tests red;
  reverted, full suite green (31). No automated mutation-testing framework is configured.

## Round-1 independent review fixes (v1.1.0)
- P2-2: exact t critical table extended df=10..30 (2.228 ... 2.042); the normal 1.96
  tail now applies only beyond df=30, where the report labels `normal-approx`; the old
  df>=10 approximation narrowed small-n CIs.
- P3-1: duplicate seed-label warning/docstring corrected — all rows of a label feed the
  last-K mean, nothing is overwritten.
- P3-2: directory mode warns on a repeated CSV stem instead of silently overwriting.
- P3-3: README states CSVs are read into memory; point it at local logs, not a multi-GB dump.
- Product: corrected the InnovationEval 43%->2% claimed-credit figure (agent-reproduces-ML
  study, not human RL seed selection); kept the verified 20.9 absolute-pp Rollout Cards
  figure with accurate wording; added rliable Related work; overlap-CI heuristic disclosed
  as "not proof of equivalence"; manual spot-check wording replaces "mutation-checked".
- New tests: exact-t vs normal-approx boundary, ci_method label, duplicate-label mean,
  duplicate-stem merge warning, approx note in report. Suite: 37 -> 43.

## Round-1 follow-up test hardening (v1.2.0)
- P3: the `intervals_overlap` boundary (`<=`) is now pinned by a test that
  constructs two CIs exactly tangent (`hi_a == lo_b`); they are still treated as
  overlapping (exit 3), so a later flip to `<` fails the suite.
- P3: SKILL.md no longer lists the df>30 normal-approx CI under WARN (exit 2); it
  is a report note that does not change the exit code.
- Suite: 43 -> 45.
