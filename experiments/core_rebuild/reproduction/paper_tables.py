#!/usr/bin/env python3
"""Generate paper tables and cell provenance from complete frozen summaries.

SPDX-License-Identifier: GPL-3.0-or-later
Standard-library only. Does not run native code, bootstrap, or change inputs.
The output directory is explicit, so portable reproduction needs no manuscript.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
from statistics import median

ROLES = ("P", "R_matched", "R_independent")
METRICS = ("task_latency_ns", "cpu_time_ns", "preprocessing_ns", "query_buffer_bytes", "reply_buffer_bytes")
BASELINES = ROLES[1:]
ROLE_TEX = {"P": "$P$", "R_matched": "$R_m$", "R_independent": "$R_i$"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message: str) -> None:
    if not condition:
        raise ValueError(message)


def resolve(document, pointer: str):
    value = document
    for key in pointer.lstrip("/").split("/"):
        key = key.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def verify_tables(summary: dict, full: list[dict], sessions: list[dict], configs: list[dict]) -> dict:
    require(summary["status"] == "COMPLETE" and summary["condition_count"] == 28 and summary["tier"] == "minimal",
            "This presentation requires the complete minimal-tier result")
    require(len(summary["conditions"]) == 28, "Condition count mismatch")
    require(len(full) == 28 * 17 and len(sessions) == 28 * 10 * 17 and len(configs) == 28 * 3,
            "Full-precision/session/configuration tables have missing or extra rows")
    seen_full, seen_session, seen_config = set(), set(), set()
    for row in full:
        key = (row["condition_id"], row["method"], row["metric"])
        require(key not in seen_full, "Duplicate full-precision statistic")
        seen_full.add(key)
        stat = resolve(summary, row["summary_pointer"])
        require([float(row[k]) for k in ("estimate", "ci95_low", "ci95_high")]
                == [stat["estimate"], *stat["CI95"]], "CSV statistic differs from summary pointer")
        c = summary["conditions"][row["condition_id"]]
        role = row["method"]
        require(row["config_id"] == c["method_roles"][role], "Full-precision config mismatch")
    for row in sessions:
        cid, role, metric, session_id = row["condition_id"], row["method"], row["metric"], int(row["session_id"])
        key = (cid, role, metric, session_id)
        require(key not in seen_session, "Duplicate session statistic")
        seen_session.add(key)
        c = summary["conditions"][cid]
        s = next(s for s in c["sessions"] if s["session_id"] == session_id)
        expected = s["ratios"][role] if metric == "paired_latency_ratio_to_P" else s["absolute"][role][metric]
        require(float(row["session_median"]) == expected, "CSV session statistic differs from summary")
        require(json.loads(row["paired_block_ids"]) == s["paired_block_ids"]
                and json.loads(row["observation_ids"]) == s["role_observation_ids"][role], "CSV session pairing/provenance differs")
    for row in configs:
        cid, role = row["condition_id"], row["method"]
        key = (cid, role)
        require(key not in seen_config, "Duplicate configuration row")
        seen_config.add(key)
        c = summary["conditions"][cid]
        cfg, counts = c["configurations"][c["method_roles"][role]], c["accounting"][role]
        require(row["config_id"] == cfg["config_id"], "Configuration ID mismatch")
        for field in ("rho_0", "concurrency", "threads"):
            require(int(row[field]) == cfg[field], "Configuration field mismatch: " + field)
        for field in ("planned_J", "actual_L", "query_count", "query_ciphertexts", "reply_ciphertexts", "query_buffer_bytes", "reply_buffer_bytes"):
            require(int(row[field]) == counts[field], "Buffer/layout field mismatch: " + field)
        require(counts["query_buffer_bytes"] == 131072 * counts["query_ciphertexts"]
                and counts["reply_buffer_bytes"] == 131072 * counts["reply_ciphertexts"]
                and counts["reply_ciphertexts"] == counts["query_count"] * counts["actual_L"], "Nonintegral actual buffer accounting")
    for cid, c in summary["conditions"].items():
        require(c["status"] == "COMPLETE" and c["expected_sessions"] == list(range(1, 11)) and len(c["sessions"]) == 10,
                "A condition does not retain all ten complete sessions")
        require(c["shared_baseline_observations"] == (c["method_roles"]["R_matched"] == c["method_roles"]["R_independent"]), "Alias flag differs")
        for role in ROLES:
            for metric in METRICS:
                require((cid, role, metric) in seen_full, "Missing absolute statistic")
                values = [s["absolute"][role][metric] for s in c["sessions"]]
                require(median(values) == c["absolute"][role][metric]["estimate"], "Absolute estimate differs from median of ten session medians")
                require(all((cid, role, metric, session) in seen_session for session in range(1, 11)), "Missing absolute session effect")
        for baseline in BASELINES:
            require((cid, baseline, "paired_latency_ratio_to_P") in seen_full, "Missing latency contrast")
            require(median(s["ratios"][baseline] for s in c["sessions"]) == c["ratios"][baseline]["estimate"], "Ratio estimate differs from median of ten session medians")
            for s in c["sessions"]:
                require(s["paired_block_ids"] == list(range(1, 7)) and len(s["paired_ratios"][baseline]) == 6,
                        "Measured paired blocks differ from frozen protocol")
                require(median(s["paired_ratios"][baseline]) == s["ratios"][baseline], "Within-session ratio median differs")
    return {"status": "PASS", "conditions": 28, "fullprecision_statistics_checked": len(full),
            "session_statistics_checked": len(sessions), "configuration_buffer_rows_checked": len(configs),
            "session_median_estimates_checked": 28 * 17, "paired_session_ratio_medians_checked": 28 * 10 * 2,
            "bootstrap_rerun": False, "native_executions": 0}


class Cells:
    def __init__(self, summary: dict):
        self.summary, self.records = summary, []

    def record(self, filename: str, row: int, column: str, rendered: str, pointers: list[str], **formatting) -> str:
        self.records.append({"file": filename, "row": row, "column": column, "rendered_tex": rendered,
                             "sources": [{"summary_pointer": p, "full_value": resolve(self.summary, p)} for p in pointers],
                             "formatting": formatting})
        return rendered

    def value(self, filename, row, column, pointer, rendered=None):
        value = resolve(self.summary, pointer)
        return self.record(filename, row, column, str(value) if rendered is None else rendered, [pointer], type="categorical_or_exact")

    def statistic(self, filename, row, column, pointer, *, interval=False, seconds=False):
        stat = resolve(self.summary, pointer)
        divisor = 1e9 if seconds else 1
        point = f"{stat['estimate'] / divisor:.3f}"
        rendered = (r"\shortstack{" + point + r"\\{[" + f"{stat['CI95'][0] / divisor:.3f},{stat['CI95'][1] / divisor:.3f}" + "]}}") if interval else point
        return self.record(filename, row, column, rendered,
                           [pointer + "/estimate"] + ([pointer + "/CI95/0", pointer + "/CI95/1"] if interval else []),
                           type="fixed_decimal", decimal_places=3, input_unit="ns" if seconds else "ratio",
                           display_unit="s" if seconds else "ratio", divisor=divisor, interval_shown=interval)


def table(caption: str, label: str, columns: str, header: str, rows: list[str], note: str = "", *,
          font_size=8.5, line_height=10.2, column_gap=3, array_stretch=1.08) -> str:
    return "\n".join([r"\begin{table}[!htbp]", r"\centering", r"\caption{" + caption + "}", r"\label{" + label + "}",
                       r"\begingroup", rf"\fontsize{{{font_size}}}{{{line_height}}}\selectfont",
                       rf"\setlength{{\tabcolsep}}{{{column_gap}pt}}",
                       rf"\renewcommand{{\arraystretch}}{{{array_stretch}}}", r"\begin{tabular}{@{}" + columns + "@{}}", r"\toprule",
                       header + r" \\", r"\midrule", *rows, r"\bottomrule", r"\end{tabular}", r"\endgroup",
                       (rf"\par\smallskip{{\fontsize{{{font_size}}}{{{line_height}}}\selectfont " + note + "}") if note else "", r"\end{table}", ""])


def build_tables(summary: dict, cells: Cells) -> dict[str, str]:
    assets = {}
    for study, filename, label in (("primary", "primary_results.tex", "tab:core-primary-results"),
                                   ("capacity", "capacity_results.tex", "tab:core-capacity-results")):
        selected = sorted((c for c in summary["conditions"].values() if c["workload"]["study"] == study),
                          key=lambda c: (c["scope"] == "included", c["workload"]["alpha"], c["workload"]["ell_bits"]))
        require(len(selected) == (12 if study == "primary" else 16), "Incomplete presentation matrix")
        rows = []
        for index, c in enumerate(selected, 1):
            p = "/conditions/" + c["condition_id"]
            values = [cells.value(filename, index, "alpha", p + "/workload/alpha"),
                      cells.value(filename, index, "ell_bits", p + "/workload/ell_bits", f"{c['workload']['ell_bits']:,}"),
                      cells.value(filename, index, "scope", p + "/scope", "Incl." if c["scope"] == "included" else "Excl.")]
            values += [cells.statistic(filename, index, role + "_latency_s", p + "/absolute/" + role + "/task_latency_ns", seconds=True) for role in ROLES]
            values += [cells.statistic(filename, index, role + "_paired_ratio", p + "/ratios/" + role, interval=True) for role in BASELINES]
            rows.append(" & ".join(values) + r" \\")
            if index < len(selected) and selected[index - 1]["scope"] != selected[index]["scope"]:
                rows.append(r"\addlinespace[4pt]")
        last_role = "$R_i$" if study == "primary" else "$R_f$"
        caption = ("Complete primary retrieval results at $N=1024$: independently tuned repeated retrieval ($R_i$) and matched-layout repeated retrieval ($R_m$) versus packed retrieval ($P$)."
                   if study == "primary" else "Complete fixed-policy capacity results at $N=1024$: matched-layout repeated retrieval ($R_m$) and full-width repeated retrieval ($R_f$) versus packed retrieval ($P$).")
        caption += " Absolute task latencies are in seconds. Brackets are pointwise 95\\% whole-session percentile intervals for paired latency ratios; values above one favor packed retrieval."
        note = "Each estimate is the median across ten within-session medians. Complete absolute-time intervals and all ten session effects accompany the fixed data."
        ratio_header = "$R_i/P$" if study == "primary" else "$R_f/P$"
        assets[filename] = table(caption, label, "rrlrrrcc", r"$\alpha$ & $\ell$ (bits) & Scope & $P$ (s) & $R_m$ (s) & " + last_role + " (s) & $R_m/P$ & " + ratio_header, rows, note)
    filename = "costs.tex"
    selected = sorted((c for c in summary["conditions"].values() if c["workload"]["study"] == "primary" and c["workload"]["ell_bits"] == 32768),
                      key=lambda c: (c["scope"] == "included", c["workload"]["alpha"]))
    require(len(selected) == 6, "Predeclared cost slice incomplete")
    rows = []
    for index, c in enumerate(selected, 1):
        p = "/conditions/" + c["condition_id"]
        if index in (1, 4):
            if index == 4:
                rows.append(r"\addlinespace[6pt]")
            rows.append(r"\multicolumn{5}{@{}l}{Preprocessing " + c["scope"] + r"} \\")
            rows.append(r"\addlinespace[3pt]")
        values = [cells.value(filename, index, "alpha", p + "/workload/alpha")]
        for metric in ("cpu_time_ns", "preprocessing_ns"):
            for role in ("P", "R_independent"):
                pointer = p + "/absolute/" + role + "/" + metric
                stat = resolve(summary, pointer)
                point, low, high = [f"{v / 1e9:.3f}" for v in (stat["estimate"], *stat["CI95"])]
                rendered = (r"\shortstack{\makebox[3em][r]{" + point
                            + r"}\\{\fontsize{9}{10.8}\selectfont [" + low + ", " + high + "]}}")
                values.append(cells.record(filename, index, role + "_" + metric, rendered,
                    [pointer + "/estimate", pointer + "/CI95/0", pointer + "/CI95/1"],
                    type="fixed_decimal", decimal_places=3, input_unit="ns", display_unit="s", divisor=1e9,
                    interval_shown=True, scope=c["scope"], method=role, config_id=c["method_roles"][role],
                    physical_column=len(values) + 1, point_font_pt=10, interval_font_pt=9))
        rows.append(" & ".join(values) + r" \\")
        if index not in (3, 6):
            rows.append(r"\addlinespace[3pt]")
    caption = r"CPU time and preprocessing wall time for retrieving $\alpha$ records at $N=1024$ and $\ell=32768$ bits."
    note = (r"Entries show median estimates with approximate pointwise 95\% intervals; "
            "Repeated denotes independently tuned repeated retrieval.")
    assets[filename] = "\n".join([
        r"\begin{table}[!htbp]", r"\centering", r"\caption{" + caption + "}", r"\label{tab:core-costs}",
        r"\begingroup", r"\fontsize{10}{12}\selectfont", r"\setlength{\tabcolsep}{5pt}",
        r"\renewcommand{\arraystretch}{1.12}",
        r"\begin{tabular*}{\linewidth}{@{\extracolsep{\fill}}rcccc@{}}", r"\toprule",
        r"$\alpha$ & \multicolumn{2}{c}{CPU time (s)} & \multicolumn{2}{c}{Preprocessing wall time (s)} \\",
        r"\cmidrule(lr){2-3}\cmidrule(l){4-5}",
        r"& Packed & Repeated & Packed & Repeated \\", r"\midrule", *rows, r"\bottomrule",
        r"\end{tabular*}", r"\par\smallskip\noindent\parbox{\linewidth}{\raggedright " + note + "}",
        r"\endgroup", r"\end{table}", ""])
    filename = "selected_configurations.tex"
    selected = sorted((c for c in summary["conditions"].values() if c["workload"]["study"] == "primary" and c["scope"] == "excluded"),
                      key=lambda c: (c["workload"]["alpha"], c["workload"]["ell_bits"]))
    require(len(selected) == 6, "Selected workload configurations incomplete")
    rows = []
    for index, c in enumerate(selected, 1):
        cid, p = c["condition_id"], "/conditions/" + c["condition_id"]
        other = summary["conditions"][cid.removesuffix("_excluded") + "_included"]
        require(c["method_roles"] == other["method_roles"] and c["configurations"] == other["configurations"], "Configuration changed between timing scopes")
        values = [cells.value(filename, index, "alpha", p + "/workload/alpha"),
                  cells.value(filename, index, "ell_bits", p + "/workload/ell_bits", f"{c['workload']['ell_bits']:,}")]
        for role in ROLES:
            cfgid = c["method_roles"][role]
            pointers = [p + "/configurations/" + cfgid + "/" + field for field in ("rho_0", "concurrency", "threads")]
            pointers += [p + "/accounting/" + role + "/actual_L"]
            values.append(cells.record(filename, index, role + "_configuration", "/".join(str(resolve(summary, ptr)) for ptr in pointers), pointers,
                                       type="exact_tuple", order=["rho_0", "concurrency", "threads_per_query", "actual_L"]))
        rows.append(" & ".join(values) + r" \\")
    caption = r"Selected primary configurations at $N=1024$, shared by both timing scopes. Each entry is $\rho_0/c/u/L$: segment width, concurrent query processes, reply threads per query and actual blocks per query."
    note = "Selection uses separate preprocessing-excluded tuning trials. $P$ is packed, $R_m$ has matched layout, and $R_i$ is independently tuned. Actual $L$ is verified from ciphertext-buffer readback."
    assets[filename] = table(caption, "tab:core-selected-configurations", "rrccc", r"$\alpha$ & $\ell$ (bits) & $P$: $\rho_0/c/u/L$ & $R_m$: $\rho_0/c/u/L$ & $R_i$: $\rho_0/c/u/L$", rows, note)
    return assets


def session_diagnostics(summary: dict) -> dict:
    result = {}
    for cid, c in summary["conditions"].items():
        record = {"absolute_latency_s": {}, "ratios": {}}
        for role in ROLES:
            values = [s["absolute"][role]["task_latency_ns"] / 1e9 for s in c["sessions"]]
            record["absolute_latency_s"][role] = {"all_ten": values, "range": [min(values), max(values)],
                                                       "first_to_last_change_percent": (values[-1] / values[0] - 1) * 100}
        for role in BASELINES:
            values = [s["ratios"][role] for s in c["sessions"]]
            record["ratios"][role] = {"all_ten": values, "range": [min(values), max(values)],
                                      "first_to_last_change_percent": (values[-1] / values[0] - 1) * 100,
                                      "sessions_below_one": sum(v < 1 for v in values)}
        result[cid] = record
    return {"note": "Descriptive chronological diagnostics from retained session medians only; no trend test, independence claim, or changed estimator.", "conditions": result}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--summary-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    results, output = args.results.resolve(), args.out.resolve()
    require(digest(results / "summary.json") == args.summary_sha256.lower(), "Unexpected exact summary SHA")
    inputs = ["summary.json", "fullprecision.csv", "session_effects.csv", "configurations_and_buffers.csv", "analysis_provenance.json"]
    before = {name: digest(results / name) for name in inputs}
    summary = json.loads((results / "summary.json").read_text(encoding="utf-8"))
    provenance = json.loads((results / "analysis_provenance.json").read_text(encoding="utf-8"))
    require(provenance["status"] == "COMPLETE", "Incomplete analysis provenance")
    for name in inputs[:-1]:
        require(provenance["output_sha256"][name] == before[name], "Result differs from analytical provenance: " + name)
    checks = verify_tables(summary, read_csv(results / "fullprecision.csv"), read_csv(results / "session_effects.csv"), read_csv(results / "configurations_and_buffers.csv"))
    cells = Cells(summary)
    assets = build_tables(summary, cells)
    require(len(cells.records) == len({(r["file"], r["row"], r["column"]) for r in cells.records}), "Duplicate display-cell map")
    require(len(cells.records) == 284 and sum(len(r["sources"]) for r in cells.records) == 498,
            "A displayed numeric cell/source pointer is missing or added")
    for record in cells.records:
        for source in record["sources"]:
            require(resolve(summary, source["summary_pointer"]) == source["full_value"], "Display cell has a stale source pointer")
    require(all(not (output / filename).exists() for filename in [*assets, "mapping.json"]), "An existing display would be overwritten")
    output.mkdir(parents=True, exist_ok=True)
    for filename, contents in assets.items():
        with (output / filename).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(contents)
    checks.update(display_cells_checked=len(cells.records), mapping_sources_checked=sum(len(r["sources"]) for r in cells.records))
    mapping = {"schema": "CORE_PAPER_CELL_MAPPING_V1", "run_id": summary["run_id"], "status": "PASS_NUMERIC_SOURCE_CHECKS",
               "input_sha256": before, "source_sha256": digest(Path(__file__)), "checks": checks,
               "font_size_pt_by_file": {filename: (10 if filename == "costs.tex" else 8.5) for filename in assets},
               "column_gap_pt_by_file": {filename: (5 if filename == "costs.tex" else 3) for filename in assets},
               "array_stretch_by_file": {filename: (1.12 if filename == "costs.tex" else 1.08) for filename in assets},
               "visual_changes": {"costs.tex": ["10pt table and note fonts", "5pt column spacing", "1.12 array stretch",
                                                  "full linewidth; metric groups with adjacent Packed/Repeated columns",
                                                  "six data rows grouped by scope; 9pt intervals; short caption and left-aligned note"],
                                  "selected_configurations.tex": ["segment terminology in caption"]},
               "cost_layout": {"width": "linewidth", "data_rows": 6, "columns": ["alpha", "P_cpu_time_ns", "R_independent_cpu_time_ns", "P_preprocessing_ns", "R_independent_preprocessing_ns"], "row_scopes": ["excluded"] * 3 + ["included"] * 3, "row_alpha": [2, 3, 4] * 2},
               "layout_status": "Requires final manuscript compile and page inspection; no automatic shrinking",
               "predeclared_cost_slice": {"study": "primary", "N": 1024, "ell_bits": 32768, "alpha": [2, 3, 4], "scopes": ["excluded", "included"]},
               "output_sha256": {filename: digest(output / filename) for filename in assets},
               "cells": cells.records, "session_diagnostics": session_diagnostics(summary)}
    require(before == {name: digest(results / name) for name in inputs}, "A source input changed during generation")
    with (output / "mapping.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(mapping, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": mapping["status"], "output": str(output), "checks": checks, "asset_sha256": mapping["output_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
