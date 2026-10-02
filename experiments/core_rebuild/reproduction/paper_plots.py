#!/usr/bin/env python3
"""Present an explicit subset of frozen results, with complete source coverage.

SPDX-License-Identifier: GPL-3.0-or-later
This postmeasurement renderer does not modify frozen sources, estimate,
bootstrap, launch native code or read manuscript files. Focused primary axes,
capacity region labels and captions are presentation metadata; estimates,
intervals, categories and actual buffer/block counts remain unchanged.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import sys

CORE = Path(__file__).resolve().parents[1]
ROOT = CORE.parents[1]
FROZEN_RELATIVE = "experiments/core_rebuild/scripts/plots.py"
FROZEN_SHA256 = "e2c11cd376fe425e139f706839dab4c10cadc34c52bda5e98381970e62f1a501"
ANALYSIS_OUTPUTS = {"summary.json", "fullprecision.csv", "session_effects.csv",
                    "configurations_and_buffers.csv", "claim_map.json", "failure_ledger.json"}
FROZEN_FIGURE_OUTPUTS = {"retrieval_performance.pdf", "capacity_tradeoff.pdf",
                         "figure_data.json", "caption_data.json"}
MAIN_ROLE_WHITELIST = {"primary": ("R_independent",),
                       "capacity": ("P", "R_independent")}
ALL_FIGURE_ROLES = {"primary": ("R_independent", "R_matched"),
                    "capacity": ("P", "R_matched", "R_independent")}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def artist_coordinates(figure):
    """Record plotted data, limits, ticks and fonts independently of page position."""
    axes = []
    for axis in figure.axes:
        axes.append({
            "xlim": list(axis.get_xlim()), "ylim": list(axis.get_ylim()),
            "xticks": axis.get_xticks().tolist(), "yticks": axis.get_yticks().tolist(),
            "tick_text": [t.get_text() for t in (*axis.get_xticklabels(), *axis.get_yticklabels())],
            "tick_font_sizes": [t.get_fontsize() for t in (*axis.get_xticklabels(), *axis.get_yticklabels())],
            "labels": [axis.get_xlabel(), axis.get_ylabel(), axis.get_title()],
            "label_font_sizes": [axis.xaxis.label.get_fontsize(), axis.yaxis.label.get_fontsize(),
                                  axis.title.get_fontsize()],
            "lines": [{"x": line.get_xdata().tolist() if hasattr(line.get_xdata(), "tolist") else list(line.get_xdata()),
                       "y": line.get_ydata().tolist() if hasattr(line.get_ydata(), "tolist") else list(line.get_ydata()),
                       "color": line.get_color(), "marker": line.get_marker(),
                       "linestyle": line.get_linestyle(), "linewidth": line.get_linewidth(),
                       "markersize": line.get_markersize()} for line in axis.lines],
            "interval_segments": [[segment.tolist() for segment in collection.get_segments()]
                                  for collection in axis.collections if hasattr(collection, "get_segments")],
            "annotations": [{"text": t.get_text(), "position": list(t.get_position()),
                             "fontsize": t.get_fontsize()} for t in axis.texts],
        })
    return {"axes": axes,
            "figure_text": [{"text": t.get_text(), "position": list(t.get_position()),
                              "fontsize": t.get_fontsize()} for t in figure.texts]}


def point_key(point):
    return (point["condition_id"], point["method"], point["metric"])


def figure_points(figures):
    return [point for figure in figures for panel in figure["panels"]
            for series in panel["series"] for point in series["points"]]


def coverage_map(summary, frozen, baseline_data):
    """Validate all original points, then assign destinations without dropping data."""
    original = figure_points(baseline_data["figures"])
    reference = {point_key(point): point for point in original}
    require(len(original) == len(reference) == 72, "Frozen point set is incomplete or duplicated")
    regenerated = []
    rows = []
    fixed_file = "experiments/core_rebuild/results/" + summary["run_id"] + "/summary.json"
    for condition in summary["conditions"].values():
        study = condition["workload"]["study"]
        for role in ALL_FIGURE_ROLES[study]:
            point = frozen.source_point(condition, role, "task_latency_ns", ratio=(study == "primary"))
            require(reference.get(point_key(point)) == point,
                    "Original source identity/value/configuration differs: " + str(point_key(point)))
            regenerated.append(point)
            displayed = role in MAIN_ROLE_WHITELIST[study]
            figure = "retrieval_performance.pdf" if study == "primary" else "capacity_tradeoff.pdf"
            table = "Table S1 (primary results)" if study == "primary" else "Table S2 (capacity results)"
            # S1 prints ratio intervals. S2 prints absolute medians and paired
            # contrasts, not the absolute-latency intervals removed from Fig. 3.
            destinations = {
                "estimate": ([figure] if displayed else []) + [table, fixed_file],
                "CI95": ([figure] if displayed else []) +
                        ([table] if study == "primary" else []) + [fixed_file],
            }
            rows.append({"point": point, "displayed_in_main": displayed,
                         "main_figure": figure if displayed else None,
                         "destinations": destinations,
                         "fixed_data": {"path": fixed_file, "summary_pointer": point["summary_pointer"]},
                         "supplement_interval_kind": "paired ratio" if study == "primary" else "paired contrasts only; absolute CI in fixed data"})
    require({point_key(p) for p in regenerated} == set(reference), "Coverage changed the original point set")
    require(sum(row["displayed_in_main"] for row in rows) == 44 and len(rows) == 72,
            "Expected 44 main and 28 moved points")
    return rows


def draw_points(axis, points, categories, *, horizontal, scale, color, marker, style):
    """Draw the estimate and both interval endpoints independently and verify artists."""
    estimates = [point["estimate"] / scale for point in points]
    lows = [point["CI95"][0] / scale for point in points]
    highs = [point["CI95"][1] / scale for point in points]
    require(all(math.isfinite(v) for v in estimates + lows + highs) and
            all(lo <= hi for lo, hi in zip(lows, highs)), "Invalid plotted interval")
    if horizontal:
        intervals = axis.hlines(categories, lows, highs, color=color, linewidth=1.15, zorder=3)
        axis.plot(lows, categories, marker="|", markersize=4, linestyle="none", color=color)
        axis.plot(highs, categories, marker="|", markersize=4, linestyle="none", color=color)
        line, = axis.plot(estimates, categories, marker=marker, markersize=4.5,
                          linestyle=style, color=color, linewidth=1.4, zorder=4)
        expected = [[[lo, y], [hi, y]] for y, lo, hi in zip(categories, lows, highs)]
        require(list(line.get_xdata()) == estimates and list(line.get_ydata()) == list(categories),
                "Horizontal point artist differs from source")
    else:
        intervals = axis.vlines(categories, lows, highs, color=color, linewidth=1.1, zorder=3)
        axis.plot(categories, lows, marker="_", markersize=4, linestyle="none", color=color)
        axis.plot(categories, highs, marker="_", markersize=4, linestyle="none", color=color)
        line, = axis.plot(categories, estimates, marker=marker, markersize=4,
                          linestyle=style, color=color, linewidth=1.4, zorder=4)
        expected = [[[x, lo], [x, hi]] for x, lo, hi in zip(categories, lows, highs)]
        require(list(line.get_ydata()) == estimates and list(line.get_xdata()) == list(categories),
                "Vertical point artist differs from source")
    require([segment.tolist() for segment in intervals.get_segments()] == expected,
            "Interval artist differs from source endpoints")


def primary_axis_limits(summary):
    values = [value for cid in summary["figure_condition_map"]["retrieval_performance"]
              for role in MAIN_ROLE_WHITELIST["primary"]
              for value in (summary["conditions"][cid]["ratios"][role]["estimate"],
                            *summary["conditions"][cid]["ratios"][role]["CI95"])]
    require(all(math.isfinite(v) for v in values), "Nonfinite primary point/interval")
    lower = min(.95, math.floor(min(values) * 20) / 20)
    upper = max(1.35, math.ceil(max(values) * 20) / 20)
    require(lower <= min(values) and max(values) <= upper, "Focused axes would clip a scientific value")
    return [lower, upper]


def primary_figure(summary, directory, plt, frozen, limits, layouts):
    figure, axes = plt.subplots(1, 2, figsize=(6.6, 3.4), sharex=True, sharey=True)
    figure.subplots_adjust(left=.24, right=.975, bottom=.21, top=.85, wspace=.15)
    rows = [(alpha, ell) for alpha in (2, 3, 4) for ell in (4096, 32768)]
    panels = []
    for axis, scope in zip(axes, frozen.SCOPES):
        selected = [next(c for c in summary["conditions"].values()
                         if c["workload"]["study"] == "primary" and c["scope"] == scope and
                         c["workload"]["alpha"] == alpha and c["workload"]["ell_bits"] == ell)
                    for alpha, ell in rows]
        require(all(c["workload"]["N"] == 1024 for c in selected), "Primary N changed")
        points = [frozen.source_point(c, "R_independent", "", ratio=True) for c in selected]
        draw_points(axis, points, list(range(6)), horizontal=True, scale=1,
                    color=frozen.COLORS["R_independent"], marker="o", style="none")
        axis.set_xlim(*limits)
        axis.set_ylim(5.55, -.55)
        axis.set_xticks([1.0, 1.1, 1.2, 1.3], ["1.0", "1.1", "1.2", "1.3"])
        axis.set_yticks(range(6), [rf"$\alpha={alpha}$, $\ell={ell:,}$" for alpha, ell in rows])
        axis.axvline(1, color=".45", linewidth=.8, linestyle=":", zorder=1)
        for position in (1.5, 3.5):
            axis.axhline(position, color=".9", linewidth=.5, zorder=0)
        axis.grid(axis="x", color=".92", linewidth=.5, zorder=0)
        axis.set_title(frozen.SCOPE_LABELS[scope], pad=8)
        panels.append({"scope": scope, "orientation": "horizontal",
                       "workload_rows": [{"alpha": alpha, "ell_bits": ell} for alpha, ell in rows],
                       "series": [{"method": "R_independent", "points": points}]})
    axes[0].set_ylabel("Records and record length (bits)")
    figure.text(.60, .075, "Repeated / packed latency ratio (>1 favors packed)", ha="center", fontsize=8.5)
    path = directory / "retrieval_performance.pdf"
    layouts.append({"filename": path.name, "artists": artist_coordinates(figure),
                    "point_and_endpoint_artists_match_source": True})
    frozen.save_vector(figure, path)
    plt.close(figure)
    return {"filename": path.name, "width_inches": 6.6, "height_inches": 3.4,
            "minimum_font_size_pt": 8.5, "common_x_limits": limits, "panels": panels,
            "caption": "Independently tuned repeated/packed completion-latency ratios. Points are paired "
                "median-of-session-median ratios; bars are approximate pointwise 95% whole-session percentile "
                "intervals. Values above one favor packed retrieval."}


def capacity_figure(summary, directory, plt, frozen, Line2D, MaxNLocator, layouts):
    conditions = [summary["conditions"][cid] for cid in summary["figure_condition_map"]["capacity_tradeoff"]]
    upper = max(max(c["absolute"][role]["task_latency_ns"]["CI95"][1],
                    c["absolute"][role]["task_latency_ns"]["estimate"]) / 1e6
                for c in conditions for role in MAIN_ROLE_WHITELIST["capacity"]) * 1.10
    require(math.isfinite(upper) and upper > 0, "Invalid capacity limits")
    figure, axes = plt.subplots(2, 2, figsize=(6.6, 4.85), sharey=True)
    figure.subplots_adjust(left=.14, right=.975, bottom=.16, top=.83, wspace=.24, hspace=.95)
    panels = []
    for row, scope in enumerate(frozen.SCOPES):
        for column, (alpha, rho, lengths) in enumerate(((2, 12, [49144, 49152, 49160, 98304]),
                                                       (4, 6, [24568, 24576, 24584, 49152]))):
            axis = axes[row][column]
            selected = frozen.subset(summary, "capacity", scope, alpha)
            require([c["workload"]["ell_bits"] for c in selected] == lengths and
                    all(c["workload"]["N"] == 1024 for c in selected), "Capacity categories changed")
            require([c["accounting"]["P"]["actual_L"] for c in selected] == [1, 1, 2, 2] and
                    all(c["accounting"]["R_independent"]["actual_L"] == 1 for c in selected),
                    "Capacity block counts changed")
            panel = {"scope": scope, "alpha": alpha, "packed_rho_0": rho, "boundary_bits": 4096 * rho,
                     "x_type": "categorical measured record lengths; not equal-spaced continuous bits", "series": []}
            for role, marker, style in (("P", "o", "-"), ("R_independent", "^", "--")):
                points = [frozen.source_point(c, role, "task_latency_ns") for c in selected]
                draw_points(axis, points, list(range(4)), horizontal=False, scale=1e6,
                            color=frozen.COLORS[role], marker=marker, style=style)
                panel["series"].append({"method": role, "display_label": frozen.CAPACITY_LABELS[role], "points": points})
            axis.set_xticks(range(4), [f"{length:,}" for length in lengths])
            axis.set_xlim(-.20, 3.20)
            axis.set_ylim(0, upper)
            axis.axvline(1.5, color=".55", linewidth=.85, linestyle=":", zorder=1)
            axis.grid(axis="y", color=".90", linewidth=.5, zorder=0)
            axis.yaxis.set_major_locator(MaxNLocator(nbins=5))
            axis.set_title(r"$\alpha=" + str(alpha) + r",\ \rho_0=" + str(rho) + "$", pad=23)
            for position, blocks in ((.5, 1), (2.5, 2)):
                axis.text(position, 1.025, rf"Packed $L={blocks}$", transform=axis.get_xaxis_transform(),
                          ha="center", va="bottom", fontsize=8.5)
            axis.set_xlabel("Measured record length (bits; categories)")
            if column == 0:
                axis.set_ylabel(frozen.SCOPE_LABELS[scope] + "\nTask latency (ms)")
            panels.append(panel)
    handles = [Line2D([0], [0], color=frozen.COLORS[role], marker=marker, linestyle=style,
                       label=frozen.CAPACITY_LABELS[role])
               for role, marker, style in (("P", "o", "-"), ("R_independent", "^", "--"))]
    figure.legend(handles=handles, loc="upper center", bbox_to_anchor=(.56, .995), ncol=2, frameon=False)
    figure.text(.56, .035, r"Full-width repeated: $L=1$ at all measured lengths.", ha="center", fontsize=8.5)
    path = directory / "capacity_tradeoff.pdf"
    layouts.append({"filename": path.name, "artists": artist_coordinates(figure),
                    "point_and_endpoint_artists_match_source": True})
    frozen.save_vector(figure, path)
    plt.close(figure)
    return {"filename": path.name, "width_inches": 6.6, "height_inches": 4.85,
            "minimum_font_size_pt": 8.5, "common_y_limits_ms": [0, upper], "panels": panels,
            "block_region_labels": {"packed": [1, 1, 2, 2], "full_width": [1, 1, 1, 1]},
            "categorical_group_separator": {"position": 1.5, "measured_x_coordinate": False},
            "caption": "Completion latency under fixed execution policies for packed and full-width "
                "repeated retrieval. Points are medians of session medians; bars are approximate pointwise "
                "95% whole-session percentile intervals. Dotted separators divide the packed block regions; "
                "segments connect categorical measured lengths."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--summary-sha256", required=True)
    parser.add_argument("--out", required=True, type=Path,
                        help="Explicit new output directory; existing paths are refused")
    args = parser.parse_args()
    require(not (ROOT / "experiments/measurement.lock").exists(),
            "A measurement lock exists; do not render during measurement")
    require(re.fullmatch(r"[0-9a-fA-F]{64}", args.summary_sha256), "Expected SHA256 is invalid")
    results = args.results.resolve()
    out = args.out.absolute()
    require(not os.path.lexists(out), "Output directory exists; refusing overwrite")
    require(out.parent.is_dir() and out.parent.resolve() == out.parent,
            "Output parent must exist and must not be a symlink/alias")
    summary_path = results / "summary.json"
    summary_digest = sha(summary_path)
    require(summary_digest == args.summary_sha256.lower(), "Summary differs from expected SHA256")
    summary = read_json(summary_path)
    provenance_path = results / "analysis_provenance.json"
    provenance = read_json(provenance_path)
    require(summary["schema"] == "CORE_SUMMARY_V1" and
            summary["status"] == provenance["status"] == "COMPLETE", "Analysis is incomplete")
    require(summary["run_id"] == provenance["run_id"], "Analysis run identity differs")
    require(summary["condition_count"] == len(summary["conditions"]) and
            all(c["status"] == "COMPLETE" and len(c["sessions"]) == 10
                for c in summary["conditions"].values()), "Condition/session matrix is incomplete")
    require(set(provenance["output_sha256"]) == ANALYSIS_OUTPUTS, "Analysis output set differs")
    inputs = {"analysis_provenance.json": sha(provenance_path)}
    for name, digest in provenance["output_sha256"].items():
        require(sha(results / name) == digest, "Analysis output changed: " + name)
        inputs[name] = digest
    frozen_path = CORE / "scripts/plots.py"
    require(sha(frozen_path) == FROZEN_SHA256 == summary["analysis_source_sha256"][FROZEN_RELATIVE]
            == provenance["analysis_source_sha256"][FROZEN_RELATIVE], "Frozen plot source changed")
    common_path = CORE / "scripts/common.py"
    require(sha(common_path) == summary["analysis_source_sha256"]["experiments/core_rebuild/scripts/common.py"],
            "Frozen common source changed")
    baseline = results / "figures"
    baseline_provenance = read_json(baseline / "figure_provenance.json")
    require(baseline_provenance["status"] == "COMPLETE" and
            baseline_provenance["summary_sha256"] == summary_digest and
            baseline_provenance["analysis_provenance_sha256"] == inputs["analysis_provenance.json"] and
            baseline_provenance["source_sha256"] == FROZEN_SHA256 and
            set(baseline_provenance["output_sha256"]) == FROZEN_FIGURE_OUTPUTS,
            "Frozen figure provenance differs")
    baseline_pdf_checks = {}
    for name, digest in baseline_provenance["output_sha256"].items():
        path = baseline / name
        if name.endswith(".pdf") and not path.exists():
            # Public source/data releases intentionally omit generated PDFs.
            # Numeric/caption parity still uses the exact included JSON below.
            baseline_pdf_checks[name] = "NOT_DISTRIBUTED_REFERENCE_HASH_ONLY"
            continue
        require(sha(path) == digest, "Frozen figure output changed: " + name)
        inputs["figures/" + name] = digest
        if name.endswith(".pdf"):
            baseline_pdf_checks[name] = "VERIFIED_AVAILABLE_REFERENCE_BYTES"
    inputs["figures/figure_provenance.json"] = sha(baseline / "figure_provenance.json")
    baseline_data = read_json(baseline / "figure_data.json")
    require(baseline_data["summary_sha256"] == summary_digest and
            baseline_data["source_sha256"] == FROZEN_SHA256, "Frozen coordinate identity differs")
    require(summary["tier"] == "minimal" and summary["condition_count"] == 28,
            "This presentation requires all 28 complete minimal-tier conditions")
    focused_limits = primary_axis_limits(summary)
    out.mkdir(exist_ok=False)
    runtime = out / "runtime"
    runtime.mkdir()
    (runtime / "tmp").mkdir()
    (runtime / "matplotlib").mkdir()
    for name in ("TMPDIR", "TMP", "TEMP"):
        os.environ[name] = str(runtime / "tmp")
    os.environ["MPLCONFIGDIR"] = str(runtime / "matplotlib")
    os.environ["MPLBACKEND"] = "Agg"
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(CORE / "scripts"))
    spec = importlib.util.spec_from_file_location("core_frozen_paper_plot_functions", frozen_path)
    frozen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(frozen)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import MaxNLocator
    plt.rcParams.update({"font.family": "serif", "font.serif": ["DejaVu Serif"], "mathtext.fontset": "stix",
                         "font.size": 8.5, "axes.titlesize": 9, "axes.labelsize": 8.5,
                         "xtick.labelsize": 8.5, "ytick.labelsize": 8.5, "legend.fontsize": 8.5,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.linewidth": .6, "pdf.fonttype": 42, "ps.fonttype": 42})
    layouts = []
    coverage = coverage_map(summary, frozen, baseline_data)
    figures = [primary_figure(summary, out, plt, frozen, focused_limits, layouts),
               capacity_figure(summary, out, plt, frozen, Line2D, MaxNLocator, layouts)]
    displayed = figure_points(figures)
    expected = {point_key(row["point"]): row["point"] for row in coverage if row["displayed_in_main"]}
    actual = {point_key(point): point for point in displayed}
    require(len(displayed) == len(actual) == 44 and actual == expected,
            "Main points are not the exact whitelisted subset of all original points")
    point_counts = {"primary": len(figure_points(figures[:1])), "capacity": len(figure_points(figures[1:]))}
    require(point_counts == {"primary": 12, "capacity": 32}, "Primary/capacity displayed matrix differs")
    require(len(figures[0]["panels"]) == 2 and len(figures[1]["panels"]) == 4, "A panel is missing")
    expected_captions = {figure["filename"]: {"caption": figure["caption"],
                         "minimum_font_size_pt": figure["minimum_font_size_pt"],
                         "width_inches": figure["width_inches"], "height_inches": figure["height_inches"]}
                         for figure in figures}
    data = dict(baseline_data)
    data.update(schema="CORE_PAPER_FIGURE_DATA_V3", figures=figures,
                presentation_source_sha256=sha(__file__), main_role_whitelist=MAIN_ROLE_WHITELIST,
                selection="Explicit role subset; all conditions retained; selection independent of effect size",
                exact_semantic_subset_of_frozen=True, complete_original_points_in_coverage_map=72)
    write_new(out / "figure_data.json", data)
    write_new(out / "caption_data.json", expected_captions)
    write_new(out / "coverage_mapping.json", {"schema": "CORE_PAPER_FIGURE_COVERAGE_V1",
              "run_id": summary["run_id"], "summary_sha256": summary_digest,
              "frozen_figure_data_sha256": inputs["figures/figure_data.json"],
              "original_points": 72, "main_points": 44, "moved_points": 28,
              "main_role_whitelist": MAIN_ROLE_WHITELIST,
              "all_original_source_fields_exact": True, "points": coverage})
    write_new(out / "layout_mapping.json", {"schema": "CORE_PAPER_LAYOUT_MAPPING_V3",
              "run_id": summary["run_id"], "summary_sha256": summary_digest,
              "frozen_figure_data_sha256": inputs["figures/figure_data.json"],
              "figures": layouts, "exact_semantic_subset_of_frozen": True,
              "coordinate_comparison": "Semantic source keys; primary ratio moves to x axis",
              "main_role_whitelist": MAIN_ROLE_WHITELIST,
              "allowed_visual_changes": ["explicit main-series subset", "horizontal primary interval panels",
                  "axis labels", "figure notes", "capacity block-region labels", "captions", "subplot spacing"]})
    projection = sorted(displayed, key=point_key)
    write_new(out / "numeric_preservation.json", {"schema": "CORE_FIGURE_NUMERIC_PRESERVATION_V2", "status": "PASS",
              "summary_sha256": summary_digest, "reference_figure_data_sha256": inputs["figures/figure_data.json"],
              "primary_conditions": 12, "capacity_conditions": 16, "displayed_point_counts": point_counts,
              "original_points_exactly_verified": 72, "moved_points_with_destinations": 28,
              "main_role_whitelist": MAIN_ROLE_WHITELIST,
              "exact_fields_checked": ["condition_id", "workload", "scope", "method", "metric", "estimate", "CI95",
                  "configuration", "accounting", "summary_pointer", "shared_baseline_observations"],
              "main_semantic_projection_sha256": hashlib.sha256(json.dumps(projection,
                  sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
              "focused_primary_limits": focused_limits, "all_primary_estimates_and_endpoints_visible": True,
              "actual_point_and_endpoint_artists_verified": True,
              "bootstrap_rerun": False, "native_executions": 0, "source_inputs_modified": False})
    require(sha(frozen_path) == FROZEN_SHA256, "Frozen source changed during rendering")
    require(sha(common_path) == summary["analysis_source_sha256"]["experiments/core_rebuild/scripts/common.py"],
            "Frozen common source changed during rendering")
    for relative, digest in inputs.items():
        require(sha(results / relative) == digest, "Source input changed during rendering: " + relative)
    outputs = {path.name: sha(path) for path in out.iterdir() if path.is_file()}
    receipt = {"schema": "CORE_PAPER_FIGURE_PROVENANCE_V3", "status": "COMPLETE",
               "run_id": summary["run_id"], "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "renderer_sha256": sha(__file__), "frozen_plot_source_sha256": FROZEN_SHA256,
               "summary_sha256": summary_digest, "input_sha256": inputs, "output_sha256": outputs,
               "python_version": platform.python_version(), "matplotlib_version": matplotlib.__version__,
               "main_role_whitelist": MAIN_ROLE_WHITELIST,
               "displayed_point_counts": point_counts, "original_points": 72, "moved_points": 28,
               "visual_changes": {"primary_orientation": "horizontal", "primary_panels": 2,
                                  "primary_x_limits": focused_limits, "explicit_equal_latency_tick": 1.0,
                                  "capacity_labels": "packed actual block regions", "captions_updated": True},
               "exact_semantic_subset_of_frozen": True,
               "all_original_points_preserved_in_coverage_mapping": True,
               "source_inputs_modified": False, "native_executions": 0, "new_bootstrap_resamples": 0,
               "baseline_pdf_checks": baseline_pdf_checks,
               "pdf_hashes_are_new_presentation_outputs": True,
               "minimum_font_size_pt": 8.5, "final_width_inches": 6.6, "vector_pdf": True}
    write_new(out / "paper_figure_provenance.json", receipt)
    print(json.dumps({"status": "COMPLETE", "out": str(out), "summary_sha256": summary_digest,
                      "displayed_point_counts": point_counts, "moved_points": 28,
                      "exact_semantic_subset_of_frozen": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
