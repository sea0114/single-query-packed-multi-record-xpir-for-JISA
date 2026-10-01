"""Draw current results from published, frozen full-precision summaries.

SPDX-License-Identifier: GPL-3.0-or-later
No measurements, bootstrap, pooling, or estimator changes. All outputs and
Matplotlib caches are written to one new directory.
"""
from pathlib import Path
import argparse, csv, hashlib, json, math, os


def generate(root, out):
    root, out = Path(root).resolve(), Path(out).resolve()
    for name in ("artifact", "revision_notes", "data", "manifests", "native_xpir", "paper", "submission"):
        if out.is_relative_to(root / name):
            raise ValueError("Choose output outside the retained input directories")
    out.mkdir(parents=True, exist_ok=False)
    used = {}
    def read_bytes(name):
        contents = (root / name).read_bytes()
        used[name] = hashlib.sha256(contents).hexdigest()
        return contents
    def read_json(name):
        return json.loads(read_bytes(name).decode("utf-8-sig"))
    def save(name, value):
        (out / name).write_text(value + "\n", encoding="utf-8", newline="\n")
    def save_json(name, value):
        save(name, json.dumps(value, indent=2))
    primary = read_json("revision_notes/B1_primary_audit/paired_ratio_recomputed.json")["cell_results"]
    stats = read_json("revision_notes/B1_primary_audit/statistics_recomputed.json")["points"]
    scaling = read_json("revision_notes/B2_B_result_audit/scaling_audit.json")["rows"]
    frontier = read_json("revision_notes/B2_A_feasibility_frontier.json")["cells"]
    overlap = read_json("revision_notes/B2_B_result_audit/B1_B2B_sanity_details.json")["rows"]
    followup = list(csv.DictReader(read_bytes("artifact/results/B3_descriptive_v1/B3_cells.csv").decode("utf-8-sig").splitlines()))
    assert (len(primary), len(stats), len(scaling), len(frontier), len(overlap), len(followup)) == (96, 48, 8, 9, 8, 18)
    primary_points = [dict(key=[c["N"], c["ell_bits"], c["rho_0"], c["mode"]], N=c["N"], ell_bits=c["ell_bits"], rho_0=c["rho_0"], scope=c["mode"], R=c["median_paired_ratio"], CI95=c["CI95"]) for c in primary]
    multi_points = [dict(key=[c["N"], c["ell_bits"], c["view"], a], N=c["N"], ell_bits=c["ell_bits"], alpha=a, scope=c["view"], R=c[f"R{a}"], CI95=c[f"CI95_R{a}"]) for c in scaling for a in (2, 3, 4)]
    assert len({tuple(p["key"]) for p in primary_points}) == 96
    assert len({tuple(p["key"]) for p in multi_points}) == 24
    counts = {str(a): sum(p["CI95"][0] > 1 for p in multi_points if p["alpha"] == a) for a in (2, 3, 4)}
    assert counts == {"2": 3, "3": 8, "4": 8}
    assert all(p["R"] > 1 and p["CI95"][0] <= p["R"] <= p["CI95"][1] for p in primary_points + multi_points)
    all_points = primary_points + multi_points
    limits = [min(.96, math.floor((min(p["CI95"][0] for p in all_points) - .02) * 100) / 100), math.ceil((max(p["CI95"][1] for p in all_points) + .02) * 10) / 10]
    os.environ["MPLCONFIGDIR"] = str(out / "plot_cache")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.5, "axes.titlesize": 9.5, "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42, "svg.fonttype": "none"})
    def axis_style(ax, rows, panel):
        ax.set(xlim=limits, ylim=(rows - .4, -.6))
        ax.axvline(1, color=".4", lw=.9, ls="--")
        ax.set_xticks([round(1 + .1 * i, 1) for i in range(round((limits[1] - 1) * 10) + 1)])
        ax.grid(axis="x", lw=.45, color=".86")
        ax.tick_params(axis="x", labelsize=8.5)
        ax.tick_params(axis="y", length=0, labelleft=panel == 0, pad=5)
        ax.set_title(("(a) Preprocessing included", "(b) Preprocessing excluded")[panel], pad=24, loc="left")
    def row_headers(ax):
        ax.text(-.34, 1.025, r"$N$", transform=ax.transAxes, ha="right", fontsize=9)
        ax.text(-.025, 1.025, r"$\ell$ (bits)", transform=ax.transAxes, ha="right", fontsize=9)
    def save_plot(fig, name, plotted):
        fig.text(.60, .022 if name == "primary96" else .03, r"Median paired ratio $R$ (repeated / packed)", ha="center", fontsize=9.5)
        fig.savefig(out / (name + ".pdf"), metadata={"CreationDate": None, "ModDate": None, "Title": name})
        fig.savefig(out / (name + ".png"), dpi=180)
        plt.close(fig)
        save_json(name + "_data.json", plotted)
    for name, rhos, height in (("primary32", (8,), 3.7), ("primary96", (8, 12, 16), 8.7)):
        fig, axes = plt.subplots(len(rhos), 2, figsize=(6.5, height), squeeze=False)
        plotted = []
        for row, rho in enumerate(rhos):
            for panel, scope in enumerate(("COLD", "ONLINE")):
                ax = axes[row, panel]
                selected = sorted((p for p in primary_points if (p["rho_0"], p["scope"]) == (rho, scope)), key=lambda p: (p["N"], p["ell_bits"]))
                assert len(selected) == 16
                for y, point in enumerate(selected):
                    lo, hi = point["CI95"]
                    ax.plot([lo, hi], [y, y], color="#315973", lw=1.2)
                    ax.plot(point["R"], y, "o", color="#17374d", ms=3.7)
                    plotted.append(point)
                axis_style(ax, 16, panel)
                ax.set_yticks(range(16), [f"{p['ell_bits']:,}" for p in selected], fontsize=8.5)
                for y in (3.5, 7.5, 11.5):
                    ax.axhline(y, color=".85", lw=.65)
                if panel == 0:
                    row_headers(ax)
                    for first in range(0, 16, 4):
                        ax.text(-.34, first + 1.5, f"{selected[first]['N']:,}", transform=ax.get_yaxis_transform(), ha="right", va="center", fontsize=9)
                if len(rhos) > 1:
                    ax.text(.97, .95, r"$\rho_0=" + str(rho) + "$", transform=ax.transAxes, ha="right", va="top", fontsize=9)
        fig.subplots_adjust(left=.22, right=.97, bottom=.155 if len(rhos) == 1 else .09, top=.855 if len(rhos) == 1 else .945, wspace=.18, hspace=.50)
        save_plot(fig, name, plotted)
    fig, axes = plt.subplots(1, 2, figsize=(6.5, 3.55))
    plotted = []
    markers = {2: "o", 3: "s", 4: "^"}
    colors = {2: "#17374d", 3: "#a45f19", 4: "#42674c"}
    workloads = sorted({(p["N"], p["ell_bits"]) for p in multi_points})
    for panel, scope in enumerate(("COLD", "ONLINE")):
        ax = axes[panel]
        for group, (n, ell) in enumerate(workloads):
            for a in (2, 3, 4):
                point = next(p for p in multi_points if (p["N"], p["ell_bits"], p["scope"], p["alpha"]) == (n, ell, scope, a))
                y = group * 4 + a - 2
                lo, hi = point["CI95"]
                ax.plot([lo, hi], [y, y], color=colors[a], lw=1.2)
                ax.plot(point["R"], y, marker=markers[a], ms=4.3, color=colors[a], mfc="white" if a == 3 else colors[a], label=f"{a} records" if group == 0 else None)
                plotted.append(point)
            if group < 3:
                ax.axhline(group * 4 + 3, color=".85", lw=.65)
        axis_style(ax, 15, panel)
        ax.set_yticks([1, 5, 9, 13], [f"{ell:,}" for n, ell in workloads], fontsize=8.5)
        if panel == 0:
            row_headers(ax)
            for group, (n, ell) in enumerate(workloads):
                ax.text(-.34, group * 4 + 1, f"{n:,}", transform=ax.get_yaxis_transform(), ha="right", va="center", fontsize=9)
    fig.subplots_adjust(left=.22, right=.97, bottom=.16, top=.76, wspace=.18)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, title="Records retrieved", ncol=3, loc="upper center", bbox_to_anchor=(.60, 1.015), frameon=False, fontsize=9, title_fontsize=9, handlelength=1)
    save_plot(fig, "retrieval_count", plotted)
    save("primary32.tex", r'''\begin{figure}[!htbp]
\centering\includegraphics[width=.95\linewidth]{\refocusassets/primary32.pdf}
\caption{Two-record task latency: all 32 conditions at $\rho_0=8$ and $L=1$.
$N$ is the number of database records and $\ell$ their bit length.
Points are median paired repeated-to-packed ratios; bars are pointwise
95\% paired-bootstrap intervals. The panels differ in whether database
preprocessing is timed. Ratios above one favor packed retrieval.}
\label{fig:primary-performance}
\end{figure}''')
    save("retrieval_count.tex", r'''\begin{figure}[!htbp]
\centering\includegraphics[width=.95\linewidth]{\refocusassets/retrieval_count.pdf}
\caption{Two-to-four-record task latency: all 24 conditions at $\rho_0=8$,
$w=8\alpha$ and $L=1$. $N$ is the number of database records and $\ell$
their bit length. Symbols distinguish records retrieved; bars are
pointwise 95\% paired-bootstrap intervals. The ratio axis matches
Figure~\ref{fig:primary-performance}; the resource configurations differ.}
\label{fig:retrieval-count-latency}
\end{figure}''')
    save("primary96.tex", r'''\begin{figure}[p]
\centering\includegraphics[width=.98\linewidth,height=.90\textheight,keepaspectratio]{\refocusassets/primary96.pdf}
\caption{All 96 primary two-record conditions. $N$ is the number of
database records and $\ell$ their bit length. Points are median paired
ratios; bars are pointwise 95\% paired-bootstrap intervals. Panels
indicate database preprocessing included in or excluded from timing.}
\label{fig:primary-complete}
\end{figure}''')
    def table(name, caption, label, spec, header, rows, footnote=""):
        save(name, r"\begin{table}[!htbp]" + "\n" + r"\centering\small\renewcommand{\arraystretch}{1.12}" + "\n" + r"\caption{" + caption + "}\n" + r"\label{" + label + "}\n" + r"\setlength{\tabcolsep}{4pt}" + "\n" + r"\begin{tabular*}{\linewidth}{@{\extracolsep{\fill}}" + spec + "@{}}\n" + r"\toprule" + "\n" + header + "\n" + r"\midrule" + "\n" + "\n".join(rows) + "\n" + r"\bottomrule\end{tabular*}" + ("\n" + r"\par\smallskip\begin{minipage}{\linewidth}\footnotesize " + footnote + r"\end{minipage}" if footnote else "") + "\n" + r"\end{table}")
    scope_names = {"COLD": "Included", "ONLINE": "Excluded"}
    rows, absolute = [], []
    for n, ell in ((256, 256), (16384, 2048)):
        c = next(c for c in stats if (c["N"], c["ell_bits"], c["rho_0"]) == (n, ell, 8))
        for scope in ("COLD", "ONLINE"):
            point = next(p for p in primary_points if p["key"] == [n, ell, 8, scope])
            packed = c[scope]["packed"]["TaskTotal_ns"]["median"] / 1e9
            repeated = c[scope]["repeated"]["TaskTotal_ns"]["median"] / 1e9
            absolute.append(dict(N=n, ell_bits=ell, scope=scope, packed_s=packed, repeated_s=repeated, R=point["R"]))
            rows.append(f"{n:,} & {ell:,} & {scope_names[scope]} & {packed:.3f} & {repeated:.3f} & {point['R']:.3f}" + r" \\")
    table("absolute.tex", r"Absolute task latency at two workload corners, with $\rho_0=8$.", "tab:absolute", "rrlrrr", r"$N$ & $\ell$ (bits) & \shortstack{Preprocessing\\in timing} & \shortstack{Packed\\(s)} & \shortstack{Repeated\\(s)} & Paired $R$ \\", rows, "Time columns are separate method medians; their quotient is not the median paired ratio. Both timing scopes prepare a private database and use fresh client keys.")
    rows, capacity = [], []
    for ell in (4096, 8192, 12288, 16384, 65536):
        cells = [next(c for c in followup if c["study"] == "M5" and int(c["ell_bits"]) == ell and c["view"] == scope) for scope in ("COLD", "ONLINE")]
        assert cells[0]["J"] == cells[1]["J"] and cells[0]["L"] == cells[1]["L"]
        entries = []
        for c in cells:
            item = dict(key=[ell, c["view"]], ell_bits=ell, J=int(c["J"]), L=int(c["L"]), scope=c["view"], R=float(c["ratio_median"]), session_range=[float(c["observed_session_min"]), float(c["observed_session_max"])], session_medians=json.loads(c["session_medians"]), n_pairs=int(c["ratio_n"]))
            assert item["n_pairs"] == 30 and [min(item["session_medians"].values()), max(item["session_medians"].values())] == item["session_range"]
            capacity.append(item)
            lo, hi = item["session_range"]
            entries.append(f"{item['R']:.3f} [{lo:.3f}, {hi:.3f}]")
        rows.append(f"{ell:,} & {cells[0]['J']} & {cells[0]['L']} & " + " & ".join(entries) + r" \\")
    table("capacity.tex", r"Record-length results at $N=1024$, $\alpha=4$, $\rho_0=8$ and $w=32$.", "tab:capacity", "rrrcc", r"$\ell$ (bits) & $J$ & $L$ & \shortstack{Preprocessing\\included in timing} & \shortstack{Preprocessing\\excluded from timing} \\", rows, "Entries are median paired ratios with observed ranges of three successive session medians; 30 paired trials per condition. Brackets are descriptive ranges, not confidence intervals.")
    rows, support = [], []
    for a in (2, 3, 4):
        statuses = []
        for rho in (8, 12, 16):
            c = next(c for c in frontier if (c["alpha"], c["rho_0"]) == (a, rho))
            status = "Supported" if c["native_width_allowed"] and c["all_weights_representable"] else ("Weight limit" if c["native_width_allowed"] else "Weight and width limits")
            statuses.append(status)
            support.append(dict(alpha=a, rho_0=rho, status=status, w=c["w"], max_weight=c["max_weight"]))
        rows.append(str(a) + " & " + " & ".join(statuses) + r" \\")
    table("parameter_support.tex", "API support for the tested parameter combinations.", "tab:native-parameter-support", "rlll", r"$\alpha$ & $\rho_0=8$ & $\rho_0=12$ & $\rho_0=16$ \\", rows, r"The checked API admits integer weights up to $2^{32}-1$ and $1\le w\le56$. These interface restrictions are distinct from radix capacity and correctness with noise.")
    rows = []
    for c in overlap:
        values = []
        for study in ("B1", "B2B"):
            lo, hi = c[study + "_CI95"]
            values.append(f"{c[study + '_median_R']:.3f} [{lo:.3f}, {hi:.3f}]")
        rows.append(f"{c['N']:,} & {c['ell_bits']:,} & {scope_names[c['view']]} & " + " & ".join(values) + r" \\")
    table("overlap.tex", "Matched two-record conditions under distinct experimental settings.", "tab:overlap", "rrlcc", r"$N$ & $\ell$ (bits) & \shortstack{Preprocessing\\in timing} & \shortstack{Primary\\$R$ [interval]} & \shortstack{Two-to-four-record\\$R$ [interval]} \\", rows, r"Brackets are pointwise 95\% paired-bootstrap intervals. Values are rounded to three decimals; interval comparisons use full-precision endpoints. Samples from the two experiments are not pooled.")
    table("payload.tex", r"Ciphertext buffers for $N=1024$, $\ell=65536$ bits, $\alpha=4$ and $L=2$.", "tab:payload", "lrr", r"Buffer & Packed & Repeated \\", [r"Query (MiB) & 128 & 512 \\", r"Reply (KiB) & 256 & 1024 \\"], r"One ciphertext buffer is 128 KiB; KiB = 1024 bytes and MiB = $1024^2$ bytes. Serialization, framing, metadata and transport are excluded.")
    save_json("display_data.json", dict(policy="Presentation only; no measurements, resampling, pooling or estimator changes", source_sha256=used, primary=primary, multiplicity=scaling, followup=followup, overlap=overlap, frontier=frontier))
    save_json("table_data.json", dict(absolute=absolute, capacity=capacity, parameter_support=support, overlap=overlap))
    save_json("presentation_manifest.json", dict(policy="Presentation only: no measurements, bootstrap, estimator changes or pooling", inputs=used, generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), main_plot_counts={"primary32": 32, "retrieval_count": 24}, complete_primary_count=96, capacity_conditions=10, pointwise_CI_low_gt_one_by_alpha=counts, common_ratio_axis_limits=limits, primary_selection="All rho_0=8 conditions; editorial, not effect-selected or preregistered", outputs={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file()}))
    result = dict(primary_conditions=96, main_points=32, retrieval_count_points=24, capacity_conditions=10, CI_low_gt_one=counts, axis_limits=limits, new_measurements=0, bootstrap_runs=0, out=str(out))
    print(json.dumps(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="Published repository root")
    parser.add_argument("--out", type=Path, required=True, help="New output directory (must not already exist)")
    args = parser.parse_args()
    generate(args.root, args.out)


if __name__ == "__main__":
    main()
