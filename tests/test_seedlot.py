# -*- coding: utf-8 -*-
"""seedlot pure-function + CLI tests (pytest, stdlib only, no network)."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "skills" / "seedlot" / "scripts" / "seedlot.py"
sys.path.insert(0, str(SCRIPT.parent))

import seedlot as sl  # noqa: E402


# --------------------------------------------------------------------------- #
# statistics
# --------------------------------------------------------------------------- #

def test_summarize_known_values():
    vals = [10.0, 12.0, 14.0]
    s = sl.summarize(vals)
    assert s["n"] == 3
    assert s["mean"] == pytest.approx(12.0)
    assert s["std"] == pytest.approx(2.0)
    assert s["median"] == 12.0
    assert s["min"] == 10.0 and s["max"] == 14.0
    # n=3 -> df=2 -> t=4.303, sem=2/sqrt(3)=1.1547 -> half ~4.97
    assert s["ci_lo"] < 12.0 < s["ci_hi"]
    assert s["ci_hi"] - s["ci_lo"] == pytest.approx(2 * 4.303 * (2 / (3 ** 0.5)), rel=1e-3)


def test_summarize_single_value_has_zero_std():
    s = sl.summarize([7.0])
    assert s["n"] == 1
    assert s["std"] == 0.0
    assert s["ci_lo"] == s["ci_hi"] == 7.0


def test_summarize_empty_raises():
    with pytest.raises(ValueError):
        sl.summarize([])


def test_iqr_and_percentile():
    # type-7 linear interpolation: Q1=1.75, Q3=3.25 -> IQR 1.5
    assert sl.iqr([1, 2, 3, 4]) == pytest.approx(1.5)
    s = sorted([1, 2, 3, 4, 5])
    assert sl.percentile(s, 50) == 3.0


def test_t_critical_table_and_fallback():
    assert sl.t_critical(1) == pytest.approx(12.706)
    assert sl.t_critical(9) == pytest.approx(2.262)
    assert sl.t_critical(30) == pytest.approx(2.042, rel=1e-3)
    assert sl.t_critical(100) == pytest.approx(1.96)
    with pytest.raises(ValueError):
        sl.t_critical(0)


def test_t_critical_df10_is_not_normal_approx():
    # Round-1 P2-2: exact t(10)=2.228, not 1.96 (which would narrow the CI).
    assert sl.t_critical(10) == pytest.approx(2.228, rel=1e-3)
    assert sl.t_critical(10) != pytest.approx(1.96, rel=1e-3)


def test_cohens_d_zero_pooled_variance_is_none():
    assert sl.cohens_d([5, 5, 5], [6, 6, 6]) is None
    assert sl.cohens_d([1, 2], [3]) is None  # second arm n<2


def test_cohens_d_basic_sign_and_magnitude():
    d = sl.cohens_d([10, 12, 14], [0, 2, 4])
    assert d is not None
    assert d > 3.0  # separated samples -> large positive d


def test_intervals_overlap():
    assert sl.intervals_overlap(0, 1, 0.5, 1.5)
    assert not sl.intervals_overlap(0, 1, 2, 3)


def test_intervals_touch_at_boundary_still_overlap():
    # P3-1: intervals exactly tangent (hi_a == lo_b) are still treated as
    # overlapping (conservative). This pins the <= boundary: flipping it to <
    # would make these disjoint and must fail here.
    assert sl.intervals_overlap(0, 1, 1, 2)
    assert sl.intervals_overlap(1, 2, 0, 1)


def test_build_report_tangent_ci_is_failure():
    # End-to-end: two arms whose CIs just touch still fail the superiority gate.
    # Construct arm A with CI [.., 10] and arm B with CI [10, ..] via summaries.
    # Use fixed, symmetric values so the CI endpoints are computable.
    a = [9.0, 10.0, 11.0]  # mean 10, CI roughly [7.69, 12.31]
    b = [10.0, 12.0, 14.0]  # mean 12, CI roughly [9.69, 14.31] -> overlaps
    _, fails, _ = sl.build_report("method", b, ("baseline", a))
    assert any("overlap" in f.lower() for f in fails)


# --------------------------------------------------------------------------- #
# gates
# --------------------------------------------------------------------------- #

def test_gate_single_seed_fails():
    fails, warns = sl.gate_arm(sl.summarize([9.0]))
    assert any("1 seed" in f for f in fails)
    assert warns == []


def test_gate_two_seeds_warns_no_fail():
    fails, warns = sl.gate_arm(sl.summarize([10.0, 12.0]))
    assert fails == []
    assert any("n=2" in w for w in warns)


def test_gate_zero_variance_warns():
    _, warns = sl.gate_arm(sl.summarize([5.0, 5.0, 5.0]))
    assert any("zero variance" in w for w in warns)


def test_gate_three_clean_seeds_no_warn():
    fails, warns = sl.gate_arm(sl.summarize([10.0, 12.0, 14.0]))
    assert fails == [] and warns == []


# --------------------------------------------------------------------------- #
# IO: CSV loading
# --------------------------------------------------------------------------- #

def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def test_directory_mode_takes_last_row_per_file(tmp_path: Path):
    d = tmp_path / "runs"
    d.mkdir()
    _write_csv(d / "seed_0.csv", ["step", "reward"], [[0, 1.0], [1, 9.0]])
    _write_csv(d / "seed_1.csv", ["step", "reward"], [[0, 3.0], [1, 11.0]])
    got, warns = sl.collect(d, None, None)
    assert got == {"seed_0": 9.0, "seed_1": 11.0}
    assert warns == []


def test_single_csv_seed_column_groups_last_value(tmp_path: Path):
    p = tmp_path / "all.csv"
    _write_csv(
        p,
        ["seed", "step", "return"],
        [["a", 0, 1.0], ["a", 1, 9.0], ["b", 0, 2.0], ["b", 1, 12.0]],
    )
    got, _ = sl.collect(p, None, "seed")
    assert got == {"a": 9.0, "b": 12.0}


def test_bom_and_alternate_reward_column(tmp_path: Path):
    p = tmp_path / "b.csv"
    p.write_bytes("﻿seed,score\r\na,5\r\nb,7\r\n".encode("utf-8"))
    got, _ = sl.collect(p, "score", "seed")
    assert got == {"a": 5.0, "b": 7.0}


def test_missing_reward_column_raises(tmp_path: Path):
    p = tmp_path / "x.csv"
    _write_csv(p, ["step", "loss"], [[0, 0.1]])
    with pytest.raises(ValueError, match="reward column"):
        sl.collect(p, None, None)


def test_directory_without_csv_raises(tmp_path: Path):
    empty = tmp_path / "nope"
    empty.mkdir()
    with pytest.raises(ValueError, match="no .csv"):
        sl.collect(empty, None, None)


# ---- v2: dirty-input robustness ----

def test_non_numeric_cell_raises_with_location(tmp_path: Path):
    p = tmp_path / "x.csv"
    _write_csv(p, ["seed", "reward"], [["a", "N/A"], ["b", 7.0]])
    with pytest.raises(ValueError, match="non-numeric"):
        sl.collect(p, None, "seed")


def test_blank_rows_are_skipped(tmp_path: Path):
    p = tmp_path / "x.csv"
    p.write_text("seed,reward\na,5\n\n b , 9 \n", encoding="utf-8")
    got, _ = sl.collect(p, None, "seed")
    assert got == {"a": 5.0, "b": 9.0}


def test_duplicate_seed_label_warns_and_later_wins(tmp_path: Path):
    p = tmp_path / "x.csv"
    _write_csv(p, ["seed", "reward"], [["a", 5.0], ["a", 9.0], ["b", 3.0]])
    got, warns = sl.collect(p, None, "seed")
    assert got["a"] == 9.0
    assert any("duplicate" in w for w in warns)


# ---- v3: last-k mean ----

def test_last_k_mean_averages_tail_rows(tmp_path: Path):
    p = tmp_path / "x.csv"
    _write_csv(p, ["seed", "reward"], [["a", 1.0], ["a", 2.0], ["a", 3.0]])
    got, _ = sl.collect(p, None, "seed", last_k=2)
    assert got["a"] == pytest.approx(2.5)


def test_last_k_exceeds_length_clamps(tmp_path: Path):
    p = tmp_path / "x.csv"
    _write_csv(p, ["seed", "reward"], [["a", 1.0], ["a", 2.0]])
    got, _ = sl.collect(p, None, "seed", last_k=10)
    assert got["a"] == pytest.approx(1.5)


# --------------------------------------------------------------------------- #
# report + CLI
# --------------------------------------------------------------------------- #

def test_build_report_single_seed_lists_failure():
    report, fails, _ = sl.build_report("arm", [9.0], None)
    assert any("1 seed" in f for f in fails)
    assert "FAIL" in report


def test_build_report_overlapping_ci_is_failure():
    # arms deliberately overlap: same distribution, n=3 each
    a = [10.0, 12.0, 14.0]
    b = [11.0, 13.0, 15.0]
    _, fails, _ = sl.build_report("method", a, ("baseline", b))
    assert any("overlap" in f.lower() for f in fails)


def test_cli_clean_exit_zero(tmp_path: Path, capsys):
    d = tmp_path / "runs"
    d.mkdir()
    for i, v in enumerate([10.0, 12.0, 14.0]):
        _write_csv(d / f"seed_{i}.csv", ["step", "reward"], [[0, v - 1], [1, v]])
    code = sl.main([str(d), "--arm-name", "method"])
    assert code == 0
    out = capsys.readouterr().out
    assert "n): **3**" in out


def test_cli_single_seed_exit_three(tmp_path: Path):
    d = tmp_path / "runs"
    d.mkdir()
    _write_csv(d / "seed_0.csv", ["step", "reward"], [[0, 9.0]])
    code = sl.main([str(d)])
    assert code == 3


def test_cli_warn_exit_two(tmp_path: Path):
    d = tmp_path / "runs"
    d.mkdir()
    _write_csv(d / "seed_0.csv", ["step", "reward"], [[0, 10.0]])
    _write_csv(d / "seed_1.csv", ["step", "reward"], [[0, 12.0]])
    code = sl.main([str(d)])
    assert code == 2


def test_cli_bad_path_exit_one(tmp_path: Path):
    code = sl.main([str(tmp_path / "missing.csv")])
    assert code == 1


def test_cli_empty_directory_exit_one(tmp_path: Path):
    # P2-2: an empty directory (no .csv files) / missing data is a usage/IO
    # error -> exit 1, not a hard gate failure (exit 3); matches the README table.
    empty = tmp_path / "empty_runs"
    empty.mkdir()
    assert sl.main([str(empty)]) == 1


def test_cli_write_output_file(tmp_path: Path):
    d = tmp_path / "runs"
    d.mkdir()
    for i, v in enumerate([10.0, 12.0, 14.0]):
        _write_csv(d / f"seed_{i}.csv", ["step", "reward"], [[0, v], [1, v]])
    out = tmp_path / "report.md"
    code = sl.main([str(d), "--output", str(out)])
    assert code == 0
    assert out.read_text(encoding="utf-8").startswith("# seedlot report")


# ---- v4: machine-readable JSON ----

def test_cli_json_mode_emits_structured_payload(tmp_path: Path, capsys):
    import json as _json

    d = tmp_path / "runs"
    d.mkdir()
    for i, v in enumerate([10.0, 12.0, 14.0]):
        _write_csv(d / f"seed_{i}.csv", ["step", "reward"], [[0, v], [1, v]])
    code = sl.main([str(d), "--json"])
    assert code == 0
    payload = _json.loads(capsys.readouterr().out)
    assert payload["summary"]["n"] == 3
    assert "failures" in payload and "warnings" in payload


def test_cli_json_comparison_includes_ci_overlap(tmp_path: Path, capsys):
    import json as _json

    a = tmp_path / "a"
    a.mkdir()
    for i, v in enumerate([10.0, 12.0, 14.0]):
        _write_csv(a / f"s{i}.csv", ["step", "reward"], [[0, v]])
    b = tmp_path / "b"
    b.mkdir()
    for i, v in enumerate([11.0, 13.0, 15.0]):
        _write_csv(b / f"s{i}.csv", ["step", "reward"], [[0, v]])
    code = sl.main([str(a), "--compare", str(b), "--json"])
    assert code == 3  # overlap -> failure
    payload = _json.loads(capsys.readouterr().out)
    assert payload["comparison"]["ci_overlap"] is True


# ---- Round-1 review: finite-value fail-closed + t table ----

def test_summarize_rejects_nan_independently_of_fmean():
    # P2-1: NaN rejected at the parsing layer, not by interpreter-specific fmean.
    with pytest.raises(ValueError, match="non-finite"):
        sl.summarize([float("nan"), 13.0, 15.0])
    with pytest.raises(ValueError, match="non-finite"):
        sl.summarize([10.0, float("inf"), 14.0])


def test_to_float_rejects_nan_inf_strings():
    with pytest.raises(ValueError, match="non-finite"):
        sl._to_float("nan", "x.csv")
    with pytest.raises(ValueError, match="non-finite"):
        sl._to_float("Infinity", "x.csv")


def test_cohens_d_rejects_nan_arm_instead_of_silent_nan():
    with pytest.raises(ValueError, match="non-finite"):
        sl.cohens_d([10.0, 12.0, 14.0], [float("nan"), 13.0, 15.0])


def test_intervals_overlap_rejects_nan_bounds():
    with pytest.raises(ValueError, match="non-finite"):
        sl.intervals_overlap(float("nan"), 1.0, 0.5, 1.5)


def test_cli_nan_cell_exits_one(tmp_path: Path):
    # End-to-end: a NaN reward row must fail cleanly (exit 1), never reach CI math.
    p = tmp_path / "x.csv"
    _write_csv(p, ["seed", "reward"], [["a", "nan"], ["b", 7.0], ["c", 9.0]])
    assert sl.main([str(p), "--seed-column", "seed"]) == 1


# ---- Round-1 follow-up: t approximation boundary, duplicate labels/stems ----

def test_t_critical_df31_uses_normal_approx():
    # P2-2: exact table ends at df=30; only beyond that does 1.96 apply.
    assert sl.t_critical(30) == pytest.approx(2.042, rel=1e-3)
    assert sl.t_critical(31) == pytest.approx(1.96)
    assert sl.t_critical(100) == pytest.approx(1.96)


def test_summarize_flags_ci_method_exact_vs_approx():
    s31 = sl.summarize([float(v) for v in range(1, 32)])  # n=31 -> df=30 exact
    assert s31["ci_method"] == "exact-t"
    s32 = sl.summarize([float(v) for v in range(1, 33)])  # n=32 -> df=31 approx
    assert s32["ci_method"] == "normal-approx"


def test_duplicate_label_averages_all_rows_not_overwrite(tmp_path: Path):
    # P3-1: warning text must match behavior — all rows feed the last-K mean.
    p = tmp_path / "x.csv"
    _write_csv(p, ["seed", "reward"], [["a", 1.0], ["a", 3.0], ["b", 3.0]])
    got, warns = sl.collect(p, None, "seed", last_k=2)
    assert got["a"] == pytest.approx(2.0)  # mean of both a-rows, not last-wins
    assert any("duplicate" in w and "all matching rows" in w for w in warns)


def test_merge_part_warns_on_duplicate_stem():
    # P3-2: directory-mode repeated stem warns instead of silent overwrite.
    result: dict[str, float] = {}
    warns: list[str] = []
    sl._merge_part(result, {"seed_0": 9.0}, "seed_0.csv", warns)
    sl._merge_part(result, {"seed_0": 11.0}, "seed_0(2).csv", warns)
    assert result["seed_0"] == 11.0  # later file wins
    assert any("duplicate CSV stem" in w for w in warns)


def test_report_marks_normal_approx_ci(tmp_path: Path, capsys):
    # The Markdown report must flag the df>30 normal approximation explicitly.
    vals = [float(v) for v in range(1, 33)]
    d = tmp_path / "runs"
    d.mkdir()
    for i, v in enumerate(vals):
        _write_csv(d / f"seed_{i}.csv", ["step", "reward"], [[0, v]])
    code = sl.main([str(d)])
    assert code == 0
    out = capsys.readouterr().out
    assert "normal 1.96 tail" in out
