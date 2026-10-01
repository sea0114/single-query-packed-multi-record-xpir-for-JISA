#!/usr/bin/env python3
"""Present frozen scientific coordinates with explicit readability corrections.

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


def scientific_artist_coordinates(artists):
    """Separate plotted data from allowed limits, ticks, labels and page layout."""
    return [{key: axis[key] for key in ("xlim", "xticks", "lines", "interval_segments")}
            for axis in artists["axes"]]


def scientific_figure_fields(figures):
    """The complete condition/method/point fields must match the frozen figure."""
    return [{"filename": figure["filename"], "panels": figure["panels"]}
            for figure in figures]


def primary_axis_limits(summary):
    values = [value for cid in summary["figure_condition_map"]["retrieval_performance"]
              for role in ("R_independent", "R_matched")
              for value in (summary["conditions"][cid]["ratios"][role]["estimate"],
                            *summary["conditions"][cid]["ratios"][role]["CI95"])]
    require(all(math.isfinite(v) for v in values), "Nonfinite primary point/interval")
    lower = min(.95, math.floor(min(values) * 20) / 20)
    upper = max(1.35, math.ceil(max(values) * 20) / 20)
    require(lower <= min(values) and max(values) <= upper, "Focused axes would clip a scientific value")
    return [lower, upper]


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
    original_save = frozen.save_vector
    layout_records = []

    def save_with_paper_margin(figure, path):
        before = artist_coordinates(figure)
        old_bottom = figure.subplotpars.bottom
        if path.name == "retrieval_performance.pdf":
            for index, axis in enumerate(figure.axes):
                axis.set_ylim(*focused_limits)
                ticks = [round(i / 10, 1) for i in range(math.ceil(focused_limits[0] * 10),
                                                        math.floor(focused_limits[1] * 10) + 1)]
                require(1.0 in ticks, "Equal-latency tick is missing")
                axis.set_yticks(ticks, [f"{value:.1f}" for value in ticks])
                if index % 3 == 0:
                    scope = "excluded" if index < 3 else "included"
                    axis.set_ylabel(frozen.SCOPE_LABELS[scope] + "\nBaseline / packed latency ratio")
            for text in figure.texts:
                if "no database-size scaling evaluated" in text.get_text():
                    text.set_text(r"$N=1,024$")
        if path.name == "capacity_tradeoff.pdf":
            require(old_bottom == .145, "Unexpected frozen capacity margin")
            figure.subplots_adjust(left=.14, right=.97, bottom=.21, top=.78, wspace=.24, hspace=1.0)
            panels = [(scope, alpha) for scope in frozen.SCOPES for alpha in (2, 4)]
            for axis, (scope, alpha) in zip(figure.axes, panels, strict=True):
                selected = frozen.subset(summary, "capacity", scope, alpha)
                require(len(selected) == 4, "Capacity region lacks an actual measured category")
                require(all([c["accounting"][role]["actual_L"] for c in selected] == [1, 1, 2, 2]
                            for role in ("P", "R_matched")), "Packed/matched actual block regions differ")
                require(all(c["accounting"]["R_independent"]["actual_L"] == 1 for c in selected),
                        "Full-width actual block count differs")
                axis.set_xticks(range(4), [f"{c['workload']['ell_bits']:,}" for c in selected])
                for position, blocks in ((.5, 1), (2.5, 2)):
                    axis.text(position, 1.015, "Packed + matched\n" + rf"$L={blocks}$",
                              transform=axis.get_xaxis_transform(), ha="center", va="bottom", fontsize=8.5)
                axis.set_title(axis.get_title(), pad=32)
            for text in figure.texts:
                if text.get_text().startswith("Tick parentheses:"):
                    text.set_text(r"Full-width repeated: $L=1$ at all measured lengths.")
                elif text.get_text().startswith("Dotted separators"):
                    text.set_text(r"Dotted lines separate packed/matched $L=1$ and $L=2$ categories.")
        after = artist_coordinates(figure)
        require(scientific_artist_coordinates(after) == scientific_artist_coordinates(before),
                "Presentation correction changed point/interval/category coordinates")
        layout_records.append({"filename": path.name, "old_bottom_margin": old_bottom,
                               "new_bottom_margin": figure.subplotpars.bottom,
                               "scientific_artist_coordinates_unchanged": True, "artists": after})
        original_save(figure, path)

    frozen.save_vector = save_with_paper_margin
    figures = [frozen.primary_figure(summary, out, plt, Line2D, MaxNLocator),
               frozen.capacity_figure(summary, out, plt, Line2D, MaxNLocator)]
    require(scientific_figure_fields(figures) == scientific_figure_fields(baseline_data["figures"]),
            "Condition/method/point/interval/buffer fields changed")
    require(len(figures[0]["panels"]) == 6 and len(figures[1]["panels"]) == 4,
            "A primary/capacity panel is missing")
    figures[0]["common_y_limits"] = focused_limits
    figures[0]["minimal_tier_note"] = "N=1024"
    figures[0]["primary_y_ticks"] = [round(i / 10, 1) for i in range(math.ceil(focused_limits[0] * 10),
                                                                  math.floor(focused_limits[1] * 10) + 1)]
    figures[0]["caption"] = ("Completion latency for the full ordered task at N=1024 and w=24. "
        "Points summarize paired baseline/packed ratios by a median within each of ten sessions, followed by "
        "the median across sessions; bars are approximate pointwise 95% whole-session percentile intervals. "
        "All six panels use the same focused ratio scale, with equal latency at 1.0. Independently tuned "
        "repeated retrieval is primary; matched-layout repeated retrieval is secondary. Values above one favor "
        "packed retrieval. Complete absolute costs, configurations, buffers and all session effects accompany the fixed data.")
    figures[1]["block_region_labels"] = {"packed_and_matched": [1, 1, 2, 2], "full_width": [1, 1, 1, 1]}
    figures[1]["categorical_group_separator"] = {"between_category_indices": [1, 2],
                                                "position": 1.5, "measured_x_coordinate": False}
    figures[1]["caption"] = ("Absolute completion latency at four categorical measured record lengths around "
        "each packed block boundary, with fixed N=1024, w=24 and execution policies. The boundaries are "
        "49152 bits for two records and 24576 bits for four records. Region labels give actual blocks per query "
        "for packed and matched-layout retrieval; full-width repeated retrieval uses L=1 throughout. Dotted "
        "lines separate the one-block and two-block groups, rather than marking another measured length. "
        "Points are medians of ten within-session medians; bars are approximate pointwise 95% whole-session "
        "percentile intervals. Connecting segments guide the eye between measured categories. Complete paired "
        "contrasts and actual buffer counts accompany the fixed data.")
    expected_captions = {figure["filename"]: {"caption": figure["caption"],
                         "minimum_font_size_pt": figure["minimum_font_size_pt"],
                         "width_inches": figure["width_inches"], "height_inches": figure["height_inches"]}
                         for figure in figures}
    data = dict(baseline_data)
    data.update(schema="CORE_PAPER_FIGURE_DATA_V2", figures=figures,
                presentation_source_sha256=sha(__file__), scientific_fields_equal_to_frozen=True)
    write_new(out / "figure_data.json", data)
    write_new(out / "caption_data.json", expected_captions)
    write_new(out / "layout_mapping.json", {"schema": "CORE_PAPER_LAYOUT_MAPPING_V2",
              "run_id": summary["run_id"], "summary_sha256": summary_digest,
              "frozen_figure_data_sha256": inputs["figures/figure_data.json"],
              "figures": layout_records, "scientific_series_parity": True,
              "allowed_visual_changes": ["primary y limits/ticks", "axis labels", "figure notes",
                  "capacity block-region labels", "categorical group separator interpretation", "captions", "subplot spacing"]})
    point_counts = {"primary": sum(len(s["points"]) for p in figures[0]["panels"] for s in p["series"]),
                    "capacity": sum(len(s["points"]) for p in figures[1]["panels"] for s in p["series"])}
    require(point_counts == {"primary": 24, "capacity": 48}, "A method/contrast point is missing")
    write_new(out / "numeric_preservation.json", {"schema": "CORE_FIGURE_NUMERIC_PRESERVATION_V1", "status": "PASS",
              "summary_sha256": summary_digest, "reference_figure_data_sha256": inputs["figures/figure_data.json"],
              "primary_conditions": 12, "capacity_conditions": 16, "displayed_point_counts": point_counts,
              "exact_fields_checked": ["condition_id", "workload", "scope", "method", "estimate", "CI95",
                  "configuration", "accounting", "summary_pointer", "shared_baseline_observations"],
              "scientific_figure_projection_sha256": hashlib.sha256(json.dumps(scientific_figure_fields(figures),
                  sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
              "focused_primary_limits": focused_limits, "all_primary_estimates_and_endpoints_visible": True,
              "bootstrap_rerun": False, "native_executions": 0, "source_inputs_modified": False})
    require(sha(frozen_path) == FROZEN_SHA256, "Frozen source changed during rendering")
    for relative, digest in inputs.items():
        require(sha(results / relative) == digest, "Source input changed during rendering: " + relative)
    outputs = {path.name: sha(path) for path in out.iterdir() if path.is_file()}
    receipt = {"schema": "CORE_PAPER_FIGURE_PROVENANCE_V2", "status": "COMPLETE",
               "run_id": summary["run_id"], "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "renderer_sha256": sha(__file__), "frozen_plot_source_sha256": FROZEN_SHA256,
               "summary_sha256": summary_digest, "input_sha256": inputs, "output_sha256": outputs,
               "python_version": platform.python_version(), "matplotlib_version": matplotlib.__version__,
               "visual_changes": {"capacity_bottom_margin": {"before": .145, "after": .21},
                                  "capacity_left_margin": {"before": .105, "after": .14},
                                  "capacity_right_margin": {"before": .985, "after": .97},
                                  "capacity_top_margin": {"before": .865, "after": .78},
                                  "capacity_column_spacing": {"before": .15, "after": .24},
                                  "capacity_row_spacing": {"before": .52, "after": 1.0},
                                  "primary_y_limits": focused_limits, "explicit_equal_latency_tick": 1.0,
                                  "primary_note": "N=1024", "capacity_labels": "actual block regions",
                                  "captions_updated": True},
               "scientific_point_interval_category_buffer_fields_unchanged": True,
               "source_inputs_modified": False, "native_executions": 0, "new_bootstrap_resamples": 0,
               "baseline_pdf_checks": baseline_pdf_checks,
               "pdf_hashes_are_new_presentation_outputs": True,
               "minimum_font_size_pt": 8.5, "final_width_inches": 6.6, "vector_pdf": True}
    write_new(out / "paper_figure_provenance.json", receipt)
    print(json.dumps({"status": "COMPLETE", "out": str(out), "summary_sha256": summary_digest,
                      "scientific_fields_equal_to_frozen": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
