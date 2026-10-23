#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seedlot — honest multi-seed RL result aggregation gate.

Pure standard library (csv/math/statistics/argparse). No network, no torch,
no numpy. Given per-seed run logs (one CSV per seed, or one CSV with a seed
column), it reports n, mean, sample std, IQR, median and a 95% CI, and raises
deterministic gates for the mistakes reviewers actually flag:

  * a single seed presented as a result;
  * fewer than 3 seeds for a headline claim;
  * two arms whose 95% CIs overlap (do not claim superiority);
  * zero variance across seeds (identical values are suspicious, not robust).

This tool describes the numbers you already have. It does not run training,
does not perform hypothesis testing, and does not turn a weak experiment into
a significant one.

Exit codes (script contract):
    0  clean: no warning, no gate failure
    2  warnings present (n<3, zero variance, ...) but no hard failure
    3  hard gate failure (single seed presented, overlapping CIs)
    1  usage / IO error (missing file, empty directory/no data, malformed input)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path

# Two-sided t critical values for df = n-1, alpha=0.05 (exact table to df=30).
# Beyond df=30 a Cornish-Fisher expansion (see _t_critical_large) approximates
# the exact t quantile; it converges to the normal 1.96 tail as df grows.
_T95 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}
# Standard-normal 97.5% quantile (two-sided 95% base for the expansion).
_Z975 = 1.959963984540054

# Candidate reward column names, tried in order when --reward-column is unset.
REWARD_CANDIDATES = ("reward", "eval_return", "return", "episode_return", "mean_return", "score")


# --------------------------------------------------------------------------- #
# Pure statistics helpers (unit tested, no IO)
# --------------------------------------------------------------------------- #

def _t_critical_large(df: int) -> float:
    """t quantile for df>30 via a 4-term Cornish-Fisher expansion around the
    normal z. Error is <5e-4 vs the exact t for df>=31 (e.g. df=31 -> 2.0395,
    df=100 -> 1.9840, df=1000 -> 1.9624). This keeps the CI (and the overlap
    gate) from being artificially narrowed by a hard 1.96 at small df."""
    z = _Z975
    z3 = z * z * z
    z5 = z3 * z * z
    z7 = z5 * z * z
    nu = float(df)
    # Cornish-Fisher terms in 1/nu
    t1 = (z3 + z) / (4.0 * nu)
    t2 = (5.0 * z5 + 16.0 * z3 + 3.0 * z) / (96.0 * nu * nu)
    t3 = (3.0 * z7 + 19.0 * z5 + 17.0 * z3 - 15.0 * z) / (384.0 * nu ** 3)
    t4 = (79.0 * z ** 9 + 776.0 * z7 + 1482.0 * z5 - 1920.0 * z3 - 945.0 * z) \
        / (92160.0 * nu ** 4)
    return z + t1 + t2 + t3 + t4


def t_critical(df: int) -> float:
    """Two-sided 95% t critical value; exact table through df=30, Cornish-Fisher
    t approximation beyond that (converges to the 1.96 normal tail)."""
    if df < 1:
        raise ValueError("df must be >= 1")
    if df in _T95:
        return _T95[df]
    return _t_critical_large(df)


def _require_finite(values: list[float], what: str) -> None:
    """Reject NaN/Inf explicitly, independent of the interpreter's fmean."""
    for v in values:
        if not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError(f"non-finite value ({v!r}) in {what}; clean the log before aggregating")


def percentile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolation percentile on an already-sorted list (0..100)."""
    if not sorted_values:
        raise ValueError("empty sample")
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * (q / 100.0)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_values[lo]
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def iqr(values: list[float]) -> float:
    s = sorted(values)
    return percentile(s, 75) - percentile(s, 25)


def summarize(values: list[float]) -> dict:
    """Aggregate one arm's per-seed final returns into a summary dict.

    `values` holds one number per seed (e.g. the final-episode return of that
    seed). Raises ValueError on an empty list.
    """
    if not values:
        raise ValueError("cannot summarize an empty sample")
    _require_finite(values, "sample")
    n = len(values)
    mean = statistics.fmean(values)
    median = statistics.median(values)
    sd = statistics.stdev(values) if n > 1 else 0.0
    sem = sd / math.sqrt(n) if n else 0.0
    df = n - 1
    tcrit = t_critical(df) if n > 1 else 0.0
    half = tcrit * sem
    # Exact t table through df=30; beyond that a Cornish-Fisher t approximation
    # (accurate to <5e-4, converging to the 1.96 normal tail), flagged so the
    # reader knows the CI is not from the exact lookup table.
    ci_method = "point-only" if n == 1 else ("exact-t" if df in _T95 else "t-approx")
    s = sorted(values)
    return {
        "n": n,
        "mean": mean,
        "std": sd,
        "sem": sem,
        "ci_lo": mean - half if n > 1 else mean,
        "ci_hi": mean + half if n > 1 else mean,
        "ci_method": ci_method,
        "median": median,
        "iqr": iqr(values),
        "min": s[0],
        "max": s[-1],
        "zero_variance": sd == 0.0,
    }


def cohens_d(a: list[float], b: list[float]) -> float | None:
    """Pooled Cohen's d; None when pooled variance is zero or sample too small."""
    if len(a) < 2 or len(b) < 2:
        return None
    _require_finite(a, "cohen's d arm A")
    _require_finite(b, "cohen's d arm B")
    va = statistics.variance(a)
    vb = statistics.variance(b)
    pooled_var = ((len(a) - 1) * va + (len(b) - 1) * vb) / (len(a) + len(b) - 2)
    if pooled_var <= 0:
        return None
    pooled_sd = math.sqrt(pooled_var)
    return (statistics.fmean(a) - statistics.fmean(b)) / pooled_sd


def intervals_overlap(lo_a: float, hi_a: float, lo_b: float, hi_b: float) -> bool:
    for v in (lo_a, hi_a, lo_b, hi_b):
        if not math.isfinite(v):
            raise ValueError(f"non-finite CI bound ({v!r}); NaN cannot be tested for overlap")
    return max(lo_a, lo_b) <= min(hi_a, hi_b)


def gate_arm(summary: dict) -> tuple[list[str], list[str]]:
    """Return (failures, warnings) for a single-arm summary."""
    failures: list[str] = []
    warnings: list[str] = []
    n = summary["n"]
    if n == 0:
        failures.append("no seed values found")
    elif n == 1:
        failures.append(
            "only 1 seed: a single run is not a distribution; do not report a "
            "headline mean or superiority claim from it"
        )
    else:
        if n < 3:
            warnings.append(
                f"n={n} seeds: reviewers usually require >=3 (>=5 for a headline "
                "claim); report the full seed-level list, not only the mean"
            )
        if summary["zero_variance"]:
            warnings.append(
                "all seeds returned identical values: zero variance is suspicious "
                "(check logging/clip), it is not evidence of robustness"
            )
    return failures, warnings


def compare_arms(name_a: str, sa: dict, name_b: str, sb: dict) -> dict:
    """Compare two summaries; flag CI overlap. Cohen's d is computed by caller
    from the raw lists (this function only sees summaries)."""
    overlap = intervals_overlap(sa["ci_lo"], sa["ci_hi"], sb["ci_lo"], sb["ci_hi"])
    return {
        "arm_a": name_a,
        "arm_b": name_b,
        "mean_diff": sa["mean"] - sb["mean"],
        "ci_overlap": overlap,
        "verdict": "CI_OVERLAP" if overlap else "CI_DISJOINT",
    }


# --------------------------------------------------------------------------- #
# IO: load per-seed final returns (pure parsing, no training)
# --------------------------------------------------------------------------- #

def _pick_column(fieldnames: list[str], requested: str | None) -> str:
    if requested:
        # Exact, then case-insensitive, so --reward-column Reward still resolves.
        if requested in fieldnames:
            return requested
        ci = {f.lower(): f for f in fieldnames}
        if requested.lower() in ci:
            return ci[requested.lower()]
        raise ValueError(f"reward column '{requested}' not found; have: {fieldnames}")
    # Auto-detect: case-insensitive exact match against the candidate list.
    lower_map = {f.lower(): f for f in fieldnames}
    for cand in REWARD_CANDIDATES:
        if cand in lower_map:
            return lower_map[cand]
    raise ValueError(
        f"no reward column found (tried {REWARD_CANDIDATES}); pass --reward-column"
    )


def _to_float(cell: str, where: str) -> float:
    text = str(cell).strip()
    if text == "":
        raise ValueError(f"blank reward cell in {where}")
    try:
        v = float(text)
    except ValueError as exc:
        raise ValueError(f"non-numeric reward {text!r} in {where}") from exc
    if not math.isfinite(v):
        raise ValueError(f"non-finite reward {text!r} (NaN/Inf) in {where}; clean the log")
    return v


def _last_k_mean(values: list[float], k: int) -> float:
    """Mean of the last k values (k=1 -> final value)."""
    if k < 1:
        raise ValueError("--last-k must be >= 1")
    k = min(k, len(values))
    return statistics.fmean(values[-k:])


def csv_seed_values(
    path: Path,
    reward_column: str | None,
    seed_column: str | None,
    last_k: int = 1,
) -> tuple[dict, list[str]]:
    """Read one CSV. Returns ({seed_label: aggregated reward}, warnings).

    With a seed column -> group by label, aggregate the last `last_k` rows;
    without -> {file_stem: aggregated reward}. Duplicate labels do NOT
    overwrite: every matching row feeds that label's last-K mean, and a warning
    names the repeated label so the user can check for duplicated rows.
    """
    warnings: list[str] = []
    with path.open("r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"{path.name}: empty CSV")
        col = _pick_column(list(reader.fieldnames), reward_column)
        if seed_column:
            if seed_column not in reader.fieldnames:
                raise ValueError(f"seed column '{seed_column}' not found; have: {reader.fieldnames}")
            groups: dict[str, list[float]] = {}
            seen: set[str] = set()
            for row in reader:
                raw_label = row.get(seed_column)
                # A missing seed cell (ragged/short row) is a malformed input,
                # not a literal "None" group; reject it explicitly.
                if raw_label is None:
                    raise ValueError(
                        f"{path.name}: a row is missing its seed-column "
                        f"({seed_column!r}) value; fix the ragged row"
                    )
                label = str(raw_label).strip()
                if label == "":
                    continue
                val = _to_float(row[col], f"{path.name} seed={label}")
                if label in seen:
                    warnings.append(
                        f"{path.name}: seed label {label!r} appears more than once; "
                        "all matching rows feed the last-K mean (check for duplicated rows)"
                    )
                seen.add(label)
                groups.setdefault(label, []).append(val)
            result = {label: _last_k_mean(vals, last_k) for label, vals in groups.items()}
            return result, warnings
        rows = [r for r in reader if any(str(c).strip() for c in r.values())]
        if not rows:
            raise ValueError(f"{path.name}: no data rows")
        series = [_to_float(r[col], f"{path.name} row {i + 2}") for i, r in enumerate(rows)]
        return {path.stem: _last_k_mean(series, last_k)}, warnings


def _merge_part(result: dict[str, float], part: dict[str, float], source: str,
                warnings: list[str]) -> None:
    """Merge one file's {stem: value} into `result`; warn on a repeated stem
    instead of silently overwriting (directory mode, P3-2)."""
    for stem, value in part.items():
        if stem in result:
            warnings.append(
                f"duplicate CSV stem {stem!r} from {source}; the later file replaces "
                "the earlier value — rename files so each seed has a distinct stem"
            )
        result[stem] = value


def collect(
    seed_source: Path,
    reward_column: str | None,
    seed_column: str | None,
    last_k: int = 1,
) -> tuple[dict, list[str]]:
    """Collect ({seed_label: aggregated reward}, warnings) from dir of CSVs or one CSV."""
    result: dict[str, float] = {}
    warnings: list[str] = []
    if seed_source.is_dir():
        csv_files = sorted(p for p in seed_source.iterdir() if p.suffix.lower() == ".csv")
        if not csv_files:
            raise ValueError(f"no .csv files in {seed_source}")
        if seed_column:
            raise ValueError("--seed-column applies to a single CSV, not a directory")
        for p in csv_files:
            part, w = csv_seed_values(p, reward_column, None, last_k)
            _merge_part(result, part, p.name, warnings)
            warnings.extend(w)
    else:
        result, warnings = csv_seed_values(seed_source, reward_column, seed_column, last_k)
    return result, warnings


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

def format_summary(name: str, s: dict) -> str:
    lines = [f"### {name}", ""]
    lines.append(f"- seeds (n): **{s['n']}**")
    lines.append(f"- mean: **{s['mean']:.4f}**  (sample std {s['std']:.4f}, SEM {s['sem']:.4f})")
    if s["n"] > 1:
        lines.append(
            f"- 95% CI: [{s['ci_lo']:.4f}, {s['ci_hi']:.4f}]  "
            f"(median {s['median']:.4f}, IQR {s['iqr']:.4f})"
        )
        if s.get("ci_method") == "t-approx":
            lines.append(
                "- note: df>30, CI uses a Cornish-Fisher t approximation "
                "(accurate to <5e-4, converging to the 1.96 normal tail), not the "
                "exact lookup-table t value"
            )
        lines.append(f"- range: [{s['min']:.4f}, {s['max']:.4f}]")
    else:
        lines.append("- 95% CI: not defined for n=1 (reported point only)")
    return "\n".join(lines)


def build_report(
    arm_name: str,
    values: list[float],
    compare: tuple[str, list[float]] | None,
    extra_warnings: list[str] | None = None,
) -> tuple[str, list[str], list[str]]:
    s = summarize(values)
    failures, warnings = gate_arm(s)
    warnings.extend(extra_warnings or [])
    blocks = ["# seedlot report", ""]
    blocks.append(format_summary(arm_name, s))
    blocks.append("")

    cmp_blocks: list[str] = []
    if compare is not None:
        other_name, other_values = compare
        so = summarize(other_values)
        f2, w2 = gate_arm(so)
        failures.extend(f2)
        warnings.extend(w2)
        c = compare_arms(arm_name, s, other_name, so)
        d = cohens_d(values, other_values)
        c["cohens_d"] = d
        cmp_blocks.append(format_summary(other_name, so))
        cmp_blocks.append("")
        cmp_blocks.append(f"### comparison: {arm_name} vs {other_name}")
        cmp_blocks.append("")
        cmp_blocks.append(f"- mean difference: {c['mean_diff']:.4f}")
        if d is not None:
            cmp_blocks.append(f"- pooled Cohen's d: {d:.3f} (small |d|<0.5, medium <0.8, large >=0.8)")
        else:
            cmp_blocks.append("- pooled Cohen's d: n/a (n<2 or zero pooled variance)")
        if c["ci_overlap"]:
            failures.append(
                f"95% CIs of {arm_name} and {other_name} overlap: do NOT claim "
                "superiority; report the overlapping distributions instead"
            )
            cmp_blocks.append("- verdict: **CI OVERLAP — no superiority claim supported**")
        else:
            cmp_blocks.append("- verdict: CIs are disjoint; a directional claim is numerically "
                              "permissible, still state n, env, and scale")
    blocks.extend(cmp_blocks)

    blocks.append("")
    blocks.append("## gates")
    blocks.append("")
    if failures:
        for f in failures:
            blocks.append(f"- FAIL: {f}")
    else:
        blocks.append("- no hard failure")
    if warnings:
        for w in warnings:
            blocks.append(f"- WARN: {w}")
    elif not failures:
        blocks.append("- no warnings")
    return "\n".join(blocks) + "\n", failures, warnings


def build_json(
    arm_name: str,
    values: list[float],
    compare: tuple[str, list[float]] | None,
    extra_warnings: list[str] | None,
    failures: list[str],
    warnings: list[str],
) -> dict:
    payload: dict = {"arm": arm_name, "summary": summarize(values), "failures": failures, "warnings": warnings}
    if compare is not None:
        other_name, other_values = compare
        so = summarize(other_values)
        c = compare_arms(arm_name, payload["summary"], other_name, so)
        payload["comparison"] = {
            "arm_b": other_name,
            "summary_b": so,
            "mean_diff": c["mean_diff"],
            "ci_overlap": c["ci_overlap"],
            "cohens_d": cohens_d(values, other_values),
            "verdict": c["verdict"],
        }
    return payload


class _Parser(argparse.ArgumentParser):
    """ArgumentParser whose *usage* errors exit 1 (the argparse default is 2,
    which collides with this script's exit-code contract where 2 = warnings).
    --help still exits 0."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def main(argv: list[str] | None = None) -> int:
    ap = _Parser(description="Honest multi-seed RL aggregation gate (stdlib only).")
    ap.add_argument("source", help="directory of per-seed CSVs, or one CSV with a seed column")
    ap.add_argument("--reward-column", default=None, help="reward/return column name")
    ap.add_argument("--seed-column", default=None, help="seed column name (single-CSV mode)")
    ap.add_argument("--arm-name", default="arm", help="label for the primary arm")
    ap.add_argument("--last-k", type=int, default=1, help="mean of last K rows per seed (default 1 = final)")
    ap.add_argument("--compare", default=None, help="second arm source (dir or CSV) for comparison")
    ap.add_argument("--compare-name", default="baseline")
    ap.add_argument("--output", default=None, help="write report to this file")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON instead of Markdown")
    args = ap.parse_args(argv)

    try:
        primary, ingest_warnings = collect(Path(args.source), args.reward_column, args.seed_column, args.last_k)
        values = list(primary.values())
        compare = None
        if args.compare:
            other, other_warnings = collect(Path(args.compare), args.reward_column, args.seed_column, args.last_k)
            ingest_warnings.extend(other_warnings)
            compare = (args.compare_name, list(other.values()))
        report, failures, warnings = build_report(args.arm_name, values, compare, ingest_warnings)
        if args.json:
            payload = build_json(args.arm_name, values, compare, ingest_warnings, failures, warnings)
            rendered = json.dumps(payload, indent=2, ensure_ascii=False)
        else:
            rendered = report
        # Output writing stays inside the try so a missing/unwritable output
        # path is a clean exit-1 usage error, not an uncaught traceback.
        if args.output:
            Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        else:
            print(rendered)
    except (ValueError, OSError) as exc:
        print(f"seedlot: error: {exc}", file=sys.stderr)
        return 1

    if failures:
        return 3
    if warnings:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
