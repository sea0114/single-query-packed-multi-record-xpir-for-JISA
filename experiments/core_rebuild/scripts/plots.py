#!/usr/bin/env python3
"""Draw measured-condition vector figures from the complete frozen summary.

SPDX-License-Identifier: GPL-3.0-or-later
Requires matplotlib for presentation only. This script does not bootstrap,
estimate, tune, run native code, or read historical evidence/manuscript files.
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
from pathlib import Path
import platform

from common import CORE, ROOT, sha

COLORS = {"P": "#009E73", "R_matched": "#D55E00", "R_independent": "#0072B2"}
SCOPES = ("excluded", "included")
SCOPE_LABELS = {"excluded": "Preprocessing excluded", "included": "Preprocessing included"}
ROLES = ("P", "R_matched", "R_independent")
RATIO_LABELS = {"R_independent": "Independently tuned repeated / packed",
                "R_matched": "Matched-layout repeated / packed"}
CAPACITY_LABELS = {"P": "Packed", "R_matched": "Matched-layout repeated", "R_independent": "Full-width repeated"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def subset(summary: dict, study: str, scope: str, alpha: int) -> list[dict]:
    return sorted((c for c in summary["conditions"].values()
                   if c["workload"]["study"] == study and c["scope"] == scope and c["workload"]["alpha"] == alpha),
                  key=lambda c: (c["workload"]["ell_bits"], c["workload"]["N"]))


def source_point(condition: dict, role: str, metric: str, *, ratio: bool = False) -> dict:
    stat = condition["ratios"][role] if ratio else condition["absolute"][role][metric]
    return {"condition_id": condition["condition_id"], "workload": condition["workload"], "scope": condition["scope"],
            "method": role, "metric": "paired_latency_ratio_to_P" if ratio else metric,
            "estimate": stat["estimate"], "CI95": stat["CI95"], "configuration": condition["configurations"][condition["method_roles"][role]],
            "accounting": condition["accounting"][role], "shared_baseline_observations": condition["shared_baseline_observations"],
            "summary_pointer": f"/conditions/{condition['condition_id']}/" + (f"ratios/{role}" if ratio else f"absolute/{role}/{metric}")}


def draw_series(ax, x, stats: list[dict], *, color: str, marker: str, style: str,
                linewidth: float, elinewidth: float, capsize: float, zorder: int,
                markersize: float = 4, scale: float = 1.0) -> None:
    # Draw the interval at its own midpoint and the estimate independently.
    # A valid percentile interval need not contain its point estimate.
    require(all(s["CI95"][0] <= s["CI95"][1] and all(math.isfinite(v) for v in (s["estimate"], *s["CI95"]))
                for s in stats), "Invalid finite interval coordinates")
    centers = [(s["CI95"][0] + s["CI95"][1]) / (2 * scale) for s in stats]
    half_widths = [(s["CI95"][1] - s["CI95"][0]) / (2 * scale) for s in stats]
    ax.errorbar(x, centers, yerr=[half_widths, half_widths], fmt="none", color=color,
                elinewidth=elinewidth, capsize=capsize, zorder=zorder)
    ax.plot(x, [s["estimate"] / scale for s in stats], color=color, marker=marker,
            markersize=markersize, linestyle=style, linewidth=linewidth, zorder=zorder + 1)


def save_vector(figure, path: Path) -> None:
    # Fixed metadata avoids a changing PDF timestamp being mistaken for changed
    # scientific coordinates in a separate redraw comparison.
    figure.savefig(path, format="pdf", facecolor="white", metadata={"Title": path.stem,
                   "Creator": "core_rebuild/scripts/plots.py", "CreationDate": None, "ModDate": None})


def primary_figure(summary: dict, directory: Path, plt, Line2D, MaxNLocator) -> dict:
    minimal = summary["tier"] == "minimal"
    primary_ids = summary["figure_condition_map"]["retrieval_performance"]
    conditions = [summary["conditions"][cid] for cid in primary_ids]
    require(len(conditions) == {"full": 36, "compact": 24, "minimal": 12}[summary["tier"]], "Primary matrix incomplete")
    all_ci = [max(c["ratios"][b]["CI95"][1], c["ratios"][b]["estimate"])
              for c in conditions for b in ("R_independent", "R_matched")]
    upper = max(1.0, *all_ci) * 1.10
    figure, axes = plt.subplots(2, 3, figsize=(6.6, 4.65), sharey=True, squeeze=False)
    figure.subplots_adjust(left=.105, right=.985, bottom=.115, top=.82, wspace=.16, hspace=.43)
    panels = []
    for row, scope in enumerate(SCOPES):
        for column, alpha in enumerate((2, 3, 4)):
            ax = axes[row][column]
            selected = subset(summary, "primary", scope, alpha)
            panel = {"scope": scope, "alpha": alpha, "series": []}
            ax.axhline(1, color=".45", linewidth=.8, linestyle=":", zorder=1)
            ax.set_ylim(0, upper)
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
            ax.grid(axis="y", color=".90", linewidth=.5, zorder=0)
            ax.set_title(r"$\alpha = " + str(alpha) + "$", pad=4)
            if minimal:
                # One N cannot establish database-size scaling: use discrete
                # measured lengths and separate method points, without a line.
                require({c["workload"]["N"] for c in selected} == {1024}, "Minimal tier contains more than one N")
                lengths = sorted(c["workload"]["ell_bits"] for c in selected)
                require(lengths == [4096, 32768], "Minimal-tier record lengths incomplete")
                for baseline, offset in (("R_independent", -.045), ("R_matched", .045)):
                    stats = [c["ratios"][baseline] for c in selected]
                    x = [i + offset for i in range(2)]
                    draw_series(ax, x, stats, color=COLORS[baseline], marker="o" if baseline == "R_independent" else "s",
                                style="none", linewidth=1, elinewidth=1.1, capsize=2, zorder=3)
                    panel["series"].append({"method": baseline, "x_categories": lengths,
                                             "points": [source_point(c, baseline, "", ratio=True) for c in selected]})
                ax.set_xticks([0, 1], ["4,096", "32,768"])
                ax.set_xlim(-.30, 1.30)
                ax.set_xlabel("Record length (bits)")
            else:
                ns = sorted({c["workload"]["N"] for c in selected})
                require(ns == ({"full": [256, 1024, 4096], "compact": [256, 1024]}[summary["tier"]]), "Primary N matrix incomplete")
                ax.set_xscale("log", base=2)
                ax.set_xticks(ns, [f"{n:,}" for n in ns])
                ax.set_xlim(ns[0] / 1.18, ns[-1] * 1.18)
                for ell, marker, style in ((4096, "o", "-"), (32768, "s", "--")):
                    points = sorted((c for c in selected if c["workload"]["ell_bits"] == ell), key=lambda c: c["workload"]["N"])
                    require([c["workload"]["N"] for c in points] == ns, "An unmeasured/missing primary point would be plotted")
                    for baseline in ("R_independent", "R_matched"):
                        stats = [c["ratios"][baseline] for c in points]
                        draw_series(ax, ns, stats, color=COLORS[baseline], marker=marker, markersize=3.7, style=style,
                                    linewidth=1.8 if baseline == "R_independent" else .95,
                                    elinewidth=1.1 if baseline == "R_independent" else .8, capsize=1.8,
                                    zorder=4 if baseline == "R_independent" else 3)
                        panel["series"].append({"method": baseline, "ell_bits": ell,
                                                 "points": [source_point(c, baseline, "", ratio=True) for c in points]})
                ax.set_xlabel(r"Database records $N$")
            if column == 0:
                ax.set_ylabel(SCOPE_LABELS[scope] + "\nRepeated / packed latency")
            panels.append(panel)
    if minimal:
        handles = [Line2D([0], [0], color=COLORS[b], marker="o" if b == "R_independent" else "s", linestyle="none", label=RATIO_LABELS[b])
                   for b in ("R_independent", "R_matched")]
        figure.legend(handles=handles, loc="upper center", bbox_to_anchor=(.54, .995), ncol=1, frameon=False,
                      handlelength=1.5, columnspacing=1.0)
        figure.text(.55, .864, r"$N=1,024$; no database-size scaling evaluated", ha="center", fontsize=8.5)
    else:
        handles = [Line2D([0], [0], color=COLORS[b], marker=m, linestyle=s,
                          linewidth=1.8 if b == "R_independent" else .95,
                          label=("Independent" if b == "R_independent" else "Matched layout") + f", {ell:,} bits")
                   for b in ("R_independent", "R_matched") for ell, m, s in ((4096, "o", "-"), (32768, "s", "--"))]
        figure.legend(handles=handles, loc="upper center", bbox_to_anchor=(.54, .995), ncol=2, frameon=False,
                      handlelength=2.0, columnspacing=1.2, labelspacing=.45)
        figure.text(.55, .864, "Repeated / packed > 1: packed is faster", ha="center", fontsize=8.5)
    path = directory / "retrieval_performance.pdf"
    save_vector(figure, path)
    plt.close(figure)
    return {"filename": path.name, "width_inches": 6.6, "height_inches": 4.65,
            "minimum_font_size_pt": 8.5, "common_y_limits": [0, upper], "panels": panels,
            "caption": "Completion latency for the full ordered retrieval task at both timing scopes. Points summarize paired baseline/packed ratios by a median within each of ten sessions, followed by the median across sessions; bars are pointwise 95% whole-session percentile intervals from 10000 common resamples. Independently tuned repeated retrieval is the primary comparison; matched-layout repeated retrieval is secondary. Values above one favor packed retrieval. Only measured points are shown; connecting segments are visual guides. Complete absolute latency, CPU and preprocessing summaries, buffers, configurations and all ten session effects accompany the fixed results.",
            "minimal_tier_note": "Only N=1024 was measured; this figure does not assess N scaling." if minimal else None}


def capacity_figure(summary: dict, directory: Path, plt, Line2D, MaxNLocator) -> dict:
    capacity_ids = summary["figure_condition_map"]["capacity_tradeoff"]
    conditions = [summary["conditions"][cid] for cid in capacity_ids]
    require(len(conditions) == 16, "Capacity matrix incomplete")
    upper = max(max(c["absolute"][role]["task_latency_ns"]["CI95"][1],
                    c["absolute"][role]["task_latency_ns"]["estimate"]) / 1e6
                for c in conditions for role in ROLES) * 1.10
    require(math.isfinite(upper) and upper > 0, "Invalid capacity time limits")
    figure, axes = plt.subplots(2, 2, figsize=(6.6, 5.15), sharey=True, squeeze=False)
    figure.subplots_adjust(left=.105, right=.985, bottom=.145, top=.865, wspace=.15, hspace=.52)
    panels = []
    for row, scope in enumerate(SCOPES):
        for column, (alpha, rho, lengths) in enumerate(((2, 12, [49144, 49152, 49160, 98304]),
                                                      (4, 6, [24568, 24576, 24584, 49152]))):
            ax = axes[row][column]
            points = subset(summary, "capacity", scope, alpha)
            require([c["workload"]["ell_bits"] for c in points] == lengths, "A missing/unmeasured capacity point would be plotted")
            require(all(c["workload"]["N"] == 1024 for c in points), "Capacity N changed")
            panel = {"scope": scope, "alpha": alpha, "packed_rho_0": rho, "boundary_bits": 4096 * rho,
                     "x_type": "categorical measured record lengths; not equal-spaced continuous bits", "series": []}
            for role, marker, style in (("P", "o", "-"), ("R_matched", "s", "--"), ("R_independent", "^", "-.")):
                stats = [c["absolute"][role]["task_latency_ns"] for c in points]
                draw_series(ax, range(4), stats, color=COLORS[role], marker=marker, style=style,
                            linewidth=1.65 if role == "P" else 1.15, elinewidth=1.0, capsize=2, zorder=3, scale=1e6)
                panel["series"].append({"method": role, "points": [source_point(c, role, "task_latency_ns") for c in points]})
            tick_labels = []
            for condition in points:
                counts = condition["accounting"]
                triple = "/".join(str(counts[role]["actual_L"]) for role in ROLES)
                tick_labels.append(f"{condition['workload']['ell_bits']:,}\n({triple})")
            ax.set_xticks(range(4), tick_labels)
            ax.set_xlim(-.20, 3.20)
            ax.set_ylim(0, upper)
            ax.axvline(1.5, color=".55", linewidth=.85, linestyle=":", zorder=1)
            ax.grid(axis="y", color=".90", linewidth=.5, zorder=0)
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
            ax.set_title(r"$\alpha=" + str(alpha) + r",\ \rho_0=" + str(rho) + "$", pad=4)
            ax.set_xlabel("Measured record length (bits; categories)")
            if column == 0:
                ax.set_ylabel(SCOPE_LABELS[scope] + "\nTask latency (ms)")
            panels.append(panel)
    handles = [Line2D([0], [0], color=COLORS[r], marker=m, linestyle=s, label=CAPACITY_LABELS[r])
               for r, m, s in (("P", "o", "-"), ("R_matched", "s", "--"), ("R_independent", "^", "-."))]
    figure.legend(handles=handles, loc="upper center", bbox_to_anchor=(.54, .995), ncol=3, frameon=False,
                  handlelength=2.0, columnspacing=1.0)
    figure.text(.55, .915, r"Fixed execution policies; $N=1,024$, $w=24$", ha="center", fontsize=8.5)
    figure.text(.55, .052, "Tick parentheses: actual L for packed / matched layout / full width.", ha="center", fontsize=8.5)
    figure.text(.55, .021, "Dotted separators mark the first measured length beyond the packed block boundary.", ha="center", fontsize=8.5)
    path = directory / "capacity_tradeoff.pdf"
    save_vector(figure, path)
    plt.close(figure)
    return {"filename": path.name, "width_inches": 6.6, "height_inches": 5.15,
            "minimum_font_size_pt": 8.5, "common_y_limits_ms": [0, upper], "panels": panels,
            "caption": "Absolute completion latency across the packed block boundary, with fixed N=1024, w=24 and execution policies. Packed fragment widths are 12 bits for alpha=2 and 6 bits for alpha=4; matched-layout and full-width (24-bit) repeated methods are capacity references. Record lengths are categorical actual measurement points, including the boundary minus 8 bits, the boundary, the boundary plus 8 bits, and twice the boundary. Tick parentheses give the three methods' actual L, verified from buffer readback; reply ciphertext counts and exact buffer bytes are retained per point in figure_data.json and configurations_and_buffers.csv. Points use the median of ten within-session medians; bars are pointwise 95% whole-session percentile intervals. These fixed policies are distinct from primary-study tuning. Segments guide the eye and do not estimate unmeasured crossover locations."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--summary-sha256", required=True, help="Expected exact SHA256 of results/<run-id>/summary.json")
    args = parser.parse_args()
    require(not (ROOT / "experiments/measurement.lock").exists(), "A measurement lock exists; do not render during measurement")
    results = (CORE / "results" / args.run_id).resolve()
    require(results.parent == (CORE / "results").resolve(), "Run ID must be a single safe directory component")
    summary_path, provenance_path = results / "summary.json", results / "analysis_provenance.json"
    require(sha(summary_path) == args.summary_sha256.lower(), "Summary differs from explicitly expected SHA256")
    summary, provenance = load_json(summary_path), load_json(provenance_path)
    require(summary["schema"] == "CORE_SUMMARY_V1" and summary["status"] == provenance["status"] == "COMPLETE", "Analysis is incomplete")
    require(summary["run_id"] == provenance["run_id"] == args.run_id, "Run ID mismatch")
    require(summary["condition_count"] == len(summary["conditions"]), "Summary condition matrix incomplete")
    require(all(c["status"] == "COMPLETE" and len(c["sessions"]) == 10 for c in summary["conditions"].values()), "A formal condition is incomplete")
    for name, digest in provenance["output_sha256"].items():
        require(sha(results / name) == digest, "Analysis output changed: " + name)
    source_name = str(Path(__file__).resolve().relative_to(ROOT)).replace("\\", "/")
    require(summary["analysis_source_sha256"][source_name] == sha(__file__), "Plot source differs from summarized frozen version")
    directory = results / "figures"
    require(not directory.exists(), "Figure directory already exists; preserve existing outputs")
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
    directory.mkdir(exist_ok=False)
    figures = [primary_figure(summary, directory, plt, Line2D, MaxNLocator),
               capacity_figure(summary, directory, plt, Line2D, MaxNLocator)]
    data = {"schema": "CORE_FIGURE_DATA_V1", "run_id": args.run_id, "summary_sha256": sha(summary_path),
            "source_sha256": sha(__file__), "figure_condition_map": summary["figure_condition_map"], "figures": figures,
            "statistics": summary["statistics"], "common_joint_index_draws_sha256": summary["common_joint_index_draws_sha256"],
            "source_inputs_modified": False, "new_measurements": 0, "new_bootstrap_resamples": 0}
    write_json(directory / "figure_data.json", data)
    captions = {figure["filename"]: {"caption": figure["caption"], "minimum_font_size_pt": figure["minimum_font_size_pt"],
                                    "width_inches": figure["width_inches"], "height_inches": figure["height_inches"]} for figure in figures}
    write_json(directory / "caption_data.json", captions)
    manifest = {"schema": "CORE_FIGURE_PROVENANCE_V1", "run_id": args.run_id, "status": "COMPLETE",
                "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "summary_sha256": sha(summary_path), "analysis_provenance_sha256": sha(provenance_path),
                "source_sha256": sha(__file__), "python_version": platform.python_version(), "matplotlib_version": matplotlib.__version__,
                "output_sha256": {path.name: sha(path) for path in directory.iterdir() if path.is_file()},
                "vector_pdf": True, "no_smoothing_or_unmeasured_points": True,
                "final_width_inches": 6.6, "minimum_font_size_pt": 8.5}
    write_json(directory / "figure_provenance.json", manifest)
    print(json.dumps({"status": "COMPLETE", "figures": str(directory), "summary_sha256": sha(summary_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
