#!/usr/bin/env python3
"""Redraw frozen scientific coordinates with a separate paper layout correction.

SPDX-License-Identifier: GPL-3.0-or-later
This postmeasurement renderer does not modify frozen sources, estimate,
bootstrap, launch native code or read manuscript files. Only the capacity
figure's bottom subplot margin changes, from .145 to .21.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
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
        })
    return {"axes": axes,
            "figure_text": [{"text": t.get_text(), "position": list(t.get_position()),
                              "fontsize": t.get_fontsize()} for t in figure.texts]}


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
        if path.name == "capacity_tradeoff.pdf":
            require(old_bottom == .145, "Unexpected frozen capacity margin")
            figure.subplots_adjust(bottom=.21)
        require(artist_coordinates(figure) == before, "Margin correction changed scientific coordinates or fonts")
        layout_records.append({"filename": path.name, "old_bottom_margin": old_bottom,
                               "new_bottom_margin": figure.subplotpars.bottom,
                               "coordinates_and_fonts_unchanged": True, "artists": before})
        original_save(figure, path)

    frozen.save_vector = save_with_paper_margin
    figures = [frozen.primary_figure(summary, out, plt, Line2D, MaxNLocator),
               frozen.capacity_figure(summary, out, plt, Line2D, MaxNLocator)]
    require(figures == baseline_data["figures"], "Figure series, captions or scientific metadata changed")
    expected_captions = {figure["filename"]: {"caption": figure["caption"],
                         "minimum_font_size_pt": figure["minimum_font_size_pt"],
                         "width_inches": figure["width_inches"], "height_inches": figure["height_inches"]}
                         for figure in figures}
    require(expected_captions == read_json(baseline / "caption_data.json"), "Caption data changed")
    # Retain the exact frozen coordinate/caption files; correction provenance is
    # separate, so a formatting fix cannot masquerade as new scientific data.
    for name in ("figure_data.json", "caption_data.json"):
        with (out / name).open("xb") as stream:
            stream.write((baseline / name).read_bytes())
        require(sha(out / name) == inputs["figures/" + name], "Scientific JSON byte parity failed")
    write_new(out / "layout_mapping.json", {"schema": "CORE_PAPER_LAYOUT_MAPPING_V1",
              "run_id": summary["run_id"], "summary_sha256": summary_digest,
              "frozen_figure_data_sha256": inputs["figures/figure_data.json"],
              "figures": layout_records, "series_and_caption_parity": True})
    require(sha(frozen_path) == FROZEN_SHA256, "Frozen source changed during rendering")
    for relative, digest in inputs.items():
        require(sha(results / relative) == digest, "Source input changed during rendering: " + relative)
    outputs = {path.name: sha(path) for path in out.iterdir() if path.is_file()}
    receipt = {"schema": "CORE_PAPER_FIGURE_PROVENANCE_V1", "status": "COMPLETE",
               "run_id": summary["run_id"], "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "renderer_sha256": sha(__file__), "frozen_plot_source_sha256": FROZEN_SHA256,
               "summary_sha256": summary_digest, "input_sha256": inputs, "output_sha256": outputs,
               "python_version": platform.python_version(), "matplotlib_version": matplotlib.__version__,
               "layout_change": {"capacity_bottom_margin": {"before": .145, "after": .21}},
               "series_coordinates_fonts_limits_captions_unchanged": True,
               "source_inputs_modified": False, "native_executions": 0, "new_bootstrap_resamples": 0,
               "baseline_pdf_checks": baseline_pdf_checks,
               "primary_pdf_byte_identical_to_recorded_hash": outputs["retrieval_performance.pdf"] ==
                    baseline_provenance["output_sha256"]["retrieval_performance.pdf"],
               "minimum_font_size_pt": 8.5, "final_width_inches": 6.6, "vector_pdf": True}
    write_new(out / "paper_figure_provenance.json", receipt)
    print(json.dumps({"status": "COMPLETE", "out": str(out), "summary_sha256": summary_digest,
                      "primary_pdf_byte_identical_to_recorded_hash":
                          receipt["primary_pdf_byte_identical_to_recorded_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
