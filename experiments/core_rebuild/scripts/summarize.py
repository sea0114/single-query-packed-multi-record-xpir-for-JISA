#!/usr/bin/env python3
"""Reproduce frozen formal summaries after measurement has fully ended.

SPDX-License-Identifier: GPL-3.0-or-later
Only new core-rebuild formal observations enter this pipeline. No benchmark,
tuning, source gate, native executable, or historical result is executed/read.
Outputs are exclusive files under results/<run-id>; raw inputs are unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import datetime
import hashlib
import itertools
import json
from pathlib import Path

from analyze import BASELINES, BOOTSTRAP_RESAMPLES, KEY_FIELDS, METRICS, ROLES, analyze_condition, physical_key
from common import BACKEND_COMMIT, CORE, Q, ROOT, SEEDS, capacity_workloads, main_workloads, sha

SCHEMA = "CORE_SUMMARY_V1"
# Actual native representation: 2 ciphertext components x 2 RNS limbs x
# 4096 coefficients x 8 bytes. TaskRunner accepts native loop counters before
# marking a row COMPLETE. Count/L readback below is from measured buffer bytes.
CIPHERTEXT_BUFFER_BYTES = 131072
UNITS = {metric: "ns" if metric.endswith("_ns") else "bytes" for metric in METRICS}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def exact_integer(value, name: str, minimum: int = 0) -> int:
    require(isinstance(value, int) and not isinstance(value, bool) and value >= minimum,
            f"Invalid integer {name}")
    return value


def validate_freeze(freeze: dict) -> dict[str, dict]:
    """Validate the complete matrix and literal physical schedule, without IO."""
    require(freeze["schema"] == "CORE_FREEZE_V1", "Unsupported freeze schema")
    require(freeze["status"] == "FROZEN_NOT_FORMALLY_MEASURED", "Not a frozen design")
    require((freeze["n"], freeze["w"], freeze["t"]) == (4096, 24, 2**24), "Bottom-level parameters changed")
    require(freeze["q"] == str(Q) and freeze["backend_commit"] == BACKEND_COMMIT
            and freeze["recursion_dimension"] == freeze["database_aggregation"] == 1,
            "Pinned backend/parameter or recursion/aggregation setting changed")
    require((freeze["sessions"], freeze["warmup_blocks"], freeze["measured_blocks_per_session"]) == (10, 1, 6),
            "Frozen repetition protocol differs from ten sessions, one warmup and six measured blocks")
    require(freeze["statistics"]["bootstrap_resamples"] == BOOTSTRAP_RESAMPLES,
            "Frozen bootstrap count differs from 10000")
    require(freeze["seeds"]["bootstrap"] == SEEDS["bootstrap"], "Frozen bootstrap seed differs from declared seed")
    conditions = {c["condition_id"]: c for c in freeze["conditions"]}
    require(len(conditions) == len(freeze["conditions"]), "Duplicate frozen conditions")
    workloads = main_workloads(freeze["tier"]) + capacity_workloads()
    expected_matrix = {(w["workload_id"] + "_" + scope): (w, scope)
                       for w in workloads for scope in ("included", "excluded")}
    require(set(conditions) == set(expected_matrix), "Frozen matrix is not the complete permitted tier")
    for cid, condition in conditions.items():
        workload, scope = expected_matrix[cid]
        require(condition["workload"] == workload and condition["scope"] == scope,
                f"Frozen workload metadata differs: {cid}")
        roles, configs = condition["roles"], condition["configurations"]
        require(set(roles) == set(ROLES), f"Incomplete method roles: {cid}")
        require(set(configs) == set(roles.values()), f"Physical configurations differ from roles: {cid}")
        require(roles["P"] not in {roles[b] for b in BASELINES}, f"Packed aliases repeated: {cid}")
        require(condition["baseline_alias"] == (roles[BASELINES[0]] == roles[BASELINES[1]]),
                f"Incorrect baseline alias: {cid}")
        for role in ROLES:
            cfg = configs[roles[role]]
            require(cfg["config_id"] == roles[role], f"Config ID mismatch: {cid}/{role}")
            require(cfg["kind"] == ("P" if role == "P" else "R"), f"Wrong method kind: {cid}/{role}")
            require(cfg["n"] == freeze["n"] and cfg["w"] == freeze["w"], f"Config parameters differ: {cid}/{role}")
            rho = exact_integer(cfg["rho_0"], "rho_0", 1)
            require(rho in (4, 6, 8, 12, 16, 24), f"Unknown fragment-width candidate: {cid}/{role}")
            require(rho * (workload["alpha"] if role == "P" else 1) <= freeze["w"],
                    f"Inadmissible layout: {cid}/{role}")
            require(exact_integer(cfg["concurrency"], "concurrency", 1) * exact_integer(cfg["threads"], "threads", 1)
                    <= len(freeze["cpu_pool"]), f"Config exceeds CPU allowance: {cid}/{role}")
            require(cfg["concurrency"] == 1 if role == "P" else cfg["concurrency"] <= workload["alpha"],
                    f"Config concurrency differs from method: {cid}/{role}")
            j = (workload["ell_bits"] + rho - 1) // rho
            screen = condition["arithmetic_screens"][role]
            require(screen["strict_no_wrap"] is True and (screen["J"], screen["L"]) == (j, (j + freeze["n"] - 1) // freeze["n"]),
                    f"Frozen arithmetic screen inconsistent: {cid}/{role}")
    blocks, session_batches, literal = {}, [], []
    for block in freeze["schedule"]:
        cid, session, index = block["condition_id"], block["session_id"], block["block_id"]
        require(cid in conditions and session in range(1, 11) and index in range(7), "Schedule labels outside protocol")
        require(block["phase"] == ("warmup" if index == 0 else "measured"), "Schedule phase mismatch")
        require((cid, session, index) not in blocks, "Duplicate frozen block")
        blocks[(cid, session, index)] = block
        if not session_batches or session_batches[-1] != session:
            session_batches.append(session)
        cfgs = conditions[cid]["configurations"]
        require(len(block["order"]) == len(set(block["order"])) and set(block["order"]) == set(cfgs),
                "A block omits/duplicates physical configurations")
        targets = block["targets"]
        workload = conditions[cid]["workload"]
        require(len(targets) == workload["alpha"] and len(set(targets)) == len(targets)
                and all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < workload["N"] for i in targets),
                "Inadmissible frozen ordered targets")
        literal.extend(tuple(block[k] for k in KEY_FIELDS[:-1]) + (cfg,) for cfg in block["order"])
    require(session_batches == list(range(1, 11)), "Sessions are not ten contiguous batches")
    require(len(blocks) == len(conditions) * 10 * 7, "Frozen block matrix incomplete")
    for cid, condition in conditions.items():
        permutations = Counter(itertools.permutations(sorted(condition["configurations"])))
        require(len(condition["configurations"]) in (2, 3), "Invalid physical method count")
        if len(condition["configurations"]) == 2:
            permutations = Counter({order: 3 for order in permutations})
        for session in range(1, 11):
            require(all((cid, session, b) in blocks for b in range(7)), f"Missing session/block: {cid}/{session}")
            orders = Counter(tuple(blocks[(cid, session, b)]["order"]) for b in range(1, 7))
            require(orders == permutations, f"Unbalanced method orders: {cid}/{session}")
    expected = [physical_key(row) for row in freeze["expected_observations"]]
    require(literal == expected and len(expected) == len(set(expected)), "Expected physical observations differ from literal schedule")
    expected_maps = {
        "retrieval_performance": [c["condition_id"] for c in freeze["conditions"] if c["workload"]["study"] == "primary"],
        "capacity_tradeoff": [c["condition_id"] for c in freeze["conditions"] if c["workload"]["study"] == "capacity"],
        "costs": [c["condition_id"] for c in freeze["conditions"]],
    }
    require(freeze["figure_condition_map"] == expected_maps, "Frozen figure-to-condition map differs")
    return conditions


def validate_formal(freeze: dict, report: dict, rows: list[dict], freeze_hash: str, raw_hash: str) -> dict:
    """Refuse missing/failed data before any bootstrap or output directory."""
    conditions = validate_freeze(freeze)
    expected = [physical_key(row) for row in freeze["expected_observations"]]
    require(report["status"] == "COMPLETE", "Whole formal phase is not COMPLETE; no successful-subset summary is permitted")
    require(report["run_id"] == freeze["run_id"] and report["freeze_sha256"] == freeze_hash, "Formal report provenance mismatch")
    require(report["observations_sha256"] == raw_hash, "Formal observation SHA mismatch")
    require(report["tier"] == freeze["tier"] and report["conditions"] == len(conditions) and report["sessions"] == 10,
            "Formal report matrix metadata mismatch")
    require(report["expected_physical_tasks"] == report["executed_tasks"] == report["complete_tasks"] == len(expected),
            "Formal report physical counts incomplete")
    require(report["failed_tasks"] == report["not_started_tasks"] == 0 and not report["stopped_reason"]
            and not report["phase_errors"] and not report["preservation_errors"], "Formal report retains failure/abort/preservation errors")
    require(report["measurement_lock_acquired"] is True and report["measurement_lock_released"] is True,
            "Formal measurement lock did not complete its lifecycle")
    records = report["session_completion"]
    require([r["session_id"] for r in records] == list(range(1, 11)) and all(r["complete"] is True for r in records),
            "All ten formal sessions have not completed")
    require([physical_key(row) for row in rows] == expected, "Raw physical rows differ from complete literal expected schedule")
    require(len({row["observation_id"] for row in rows}) == len(rows), "Duplicate observation ID")
    schedule = {(b["condition_id"], b["session_id"], b["block_id"]): b for b in freeze["schedule"]}
    grouped = defaultdict(list)
    for row in rows:
        cid, cfgid = row["condition_id"], row["config_id"]
        condition = conditions[cid]
        block = schedule[(cid, row["session_id"], row["block_id"])]
        require(row["run_id"] == freeze["run_id"] and row["freeze_sha256"] == freeze_hash, "Observation provenance mismatch")
        require(row["status"] == "COMPLETE" and row["validated"] is True, "Failed or unvalidated physical observation")
        require(row["scope"] == condition["scope"] and row["workload"] == condition["workload"]
                and row["configuration"] == condition["configurations"][cfgid], "Observation configuration/workload mismatch")
        require(row["method_roles"] == [role for role, cfg in condition["roles"].items() if cfg == cfgid], "Logical aliases do not match physical observation")
        require(row["targets"] == block["targets"] and row["fixture_seed"] == block["fixture_seed"], "Paired fixture/ordered-target mismatch")
        require(row["method_order_index"] == block["order"].index(cfgid), "Actual method order differs from freeze")
        require(row["task_end_ns"] - row["task_start_ns"] == row["task_latency_ns"], "Direct task timing is inconsistent")
        expected_cpu_source = ("cgroup_v2_cpu.stat_same_task_span" if freeze["resource_policy"] == "cgroup"
                               else "coordinator_self_rusage_plus_native_G_to_D_rusage_including_exited_children")
        require(row["cpu_source"] == expected_cpu_source, "Whole-group CPU source differs from frozen resource policy")
        for metric in METRICS:
            exact_integer(row[metric], metric, 1 if metric == "task_latency_ns" else 0)
        grouped[(cid, cfgid)].append(row)
    accounting = {}
    for cid, condition in conditions.items():
        accounting[cid] = {}
        for role, cfgid in condition["roles"].items():
            physical = grouped[(cid, cfgid)]
            workload = condition["workload"]
            expected_queries = 1 if role == "P" else workload["alpha"]
            require({row["query_count"] for row in physical} == {expected_queries}, f"Actual query count differs: {cid}/{role}")
            qbytes = {row["query_buffer_bytes"] for row in physical}
            rbytes = {row["reply_buffer_bytes"] for row in physical}
            require(len(qbytes) == len(rbytes) == 1, f"Buffer accounting varies across physical observations: {cid}/{role}")
            qb, rb = next(iter(qbytes)), next(iter(rbytes))
            require(qb % CIPHERTEXT_BUFFER_BYTES == 0 and rb % (CIPHERTEXT_BUFFER_BYTES * expected_queries) == 0,
                    f"Actual buffers do not have integral ciphertext/L counts: {cid}/{role}")
            actual_query_ciphertexts = qb // CIPHERTEXT_BUFFER_BYTES
            actual_l = rb // (CIPHERTEXT_BUFFER_BYTES * expected_queries)
            screen = condition["arithmetic_screens"][role]
            require(actual_query_ciphertexts == expected_queries * workload["N"] and actual_l == screen["L"],
                    f"Readback-derived counts differ from frozen layout: {cid}/{role}")
            accounting[cid][role] = {
                "query_count": expected_queries, "query_ciphertexts": actual_query_ciphertexts,
                "reply_ciphertexts": rb // CIPHERTEXT_BUFFER_BYTES,
                "actual_L": actual_l, "planned_J": screen["J"],
                "query_buffer_bytes": qb, "reply_buffer_bytes": rb,
                "ciphertext_buffer_bytes": CIPHERTEXT_BUFFER_BYTES,
                "L_source": "raw reply_buffer_bytes / (131072 * validated query_count); verified equal to frozen L",
                "J_source": "frozen arithmetic screen; not asserted to be a new native readback",
                "buffer_source": "all complete physical observations, including warmups, have identical actual buffer bytes",
                "cpu_sources": sorted({row["cpu_source"] for row in physical}),
                "physical_observations": len(physical),
            }
    return accounting


def csv_new(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def json_new(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def tabular_rows(conditions: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    full, sessions, configs = [], [], []
    for condition in conditions:
        w = condition["workload"]
        base = {"condition_id": condition["condition_id"], "study": w["study"], "scope": condition["scope"],
                "N": w["N"], "alpha": w["alpha"], "ell_bits": w["ell_bits"],
                "shared_baseline_observations": condition["shared_baseline_observations"]}
        for role in ROLES:
            cfg = condition["configurations"][condition["method_roles"][role]]
            counts = condition["accounting"][role]
            detail = dict(base, method=role, config_id=cfg["config_id"], rho_0=cfg["rho_0"], concurrency=cfg["concurrency"],
                          threads=cfg["threads"], planned_J=counts["planned_J"], actual_L=counts["actual_L"],
                          query_count=counts["query_count"], query_ciphertexts=counts["query_ciphertexts"],
                          reply_ciphertexts=counts["reply_ciphertexts"], query_buffer_bytes=counts["query_buffer_bytes"],
                          reply_buffer_bytes=counts["reply_buffer_bytes"])
            configs.append(detail)
            for metric in METRICS:
                stat = condition["absolute"][role][metric]
                full.append(dict(detail, metric=metric, unit=UNITS[metric], estimate=stat["estimate"],
                                 ci95_low=stat["CI95"][0], ci95_high=stat["CI95"][1],
                                 estimator=condition["absolute_estimator"], summary_pointer=f"/conditions/{condition['condition_id']}/absolute/{role}/{metric}"))
        for baseline in BASELINES:
            stat = condition["ratios"][baseline]
            role_detail = next(row for row in configs[-3:] if row["method"] == baseline)
            full.append(dict(role_detail, metric="paired_latency_ratio_to_P", unit="ratio", estimate=stat["estimate"],
                             ci95_low=stat["CI95"][0], ci95_high=stat["CI95"][1], estimator=condition["estimator"],
                             summary_pointer=f"/conditions/{condition['condition_id']}/ratios/{baseline}"))
        for session in condition["sessions"]:
            for role in ROLES:
                for metric in METRICS:
                    sessions.append(dict(base, session_id=session["session_id"], method=role, config_id=condition["method_roles"][role],
                                         metric=metric, unit=UNITS[metric], session_median=session["absolute"][role][metric],
                                         paired_block_ids=json.dumps(session["paired_block_ids"], separators=(",", ":")),
                                         observation_ids=json.dumps(session["role_observation_ids"][role], separators=(",", ":"))))
            for baseline in BASELINES:
                sessions.append(dict(base, session_id=session["session_id"], method=baseline, config_id=condition["method_roles"][baseline],
                                     metric="paired_latency_ratio_to_P", unit="ratio", session_median=session["ratios"][baseline],
                                     paired_block_ids=json.dumps(session["paired_block_ids"], separators=(",", ":")),
                                     observation_ids=json.dumps(session["role_observation_ids"][baseline], separators=(",", ":"))))
    return full, sessions, configs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--freeze-sha256", required=True, help="Expected exact SHA256 of provenance/freeze.json")
    args = parser.parse_args()
    require(not (ROOT / "experiments/measurement.lock").exists(), "A measurement lock exists; do not analyze during measurement")
    run = (CORE / "runs" / args.run_id).resolve()
    output = (CORE / "results" / args.run_id).resolve()
    require(run.parent == (CORE / "runs").resolve() and output.parent == (CORE / "results").resolve(), "Run ID must be a single safe directory component")
    require(not output.exists(), "Result directory already exists; preserve existing results")
    inputs = {"freeze": run / "provenance/freeze.json", "observations": run / "raw/formal_001/observations.jsonl",
              "formal_report": run / "raw/formal_001/formal_report.json"}
    hashes = {name: sha(path) for name, path in inputs.items()}
    require(hashes["freeze"] == args.freeze_sha256.lower(), "Freeze differs from explicitly expected SHA256")
    freeze, report = load_json(inputs["freeze"]), load_json(inputs["formal_report"])
    require(freeze["run_id"] == args.run_id, "Run directory and freeze run ID differ")
    rows = load_rows(inputs["observations"])
    accounting = validate_formal(freeze, report, rows, hashes["freeze"], hashes["observations"])
    script_paths = [Path(__file__).resolve(), CORE / "scripts/analyze.py", CORE / "scripts/common.py", CORE / "scripts/plots.py"]
    scripts = {str(path.relative_to(ROOT)).replace("\\", "/"): sha(path) for path in script_paths}
    for name, digest in scripts.items():
        # Portable redraw does not require the native binary or system libraries.
        # Statistical/presentation source identity is checked when present in the
        # measurement freeze, and separately retained for every regenerated output.
        pinned = freeze["source_hashes"].get(name)
        if pinned is None:
            pinned = freeze["source_hashes"].get(name.replace("/", "\\"))
        require(pinned == digest, "Analysis/presentation source differs from frozen version: " + name)
    grouped_rows, grouped_schedule = defaultdict(list), defaultdict(list)
    for row in rows:
        grouped_rows[row["condition_id"]].append(row)
    for row in freeze["expected_observations"]:
        grouped_schedule[row["condition_id"]].append(row)
    summaries = []
    for condition in freeze["conditions"]:
        cid = condition["condition_id"]
        result = analyze_condition(grouped_rows[cid], grouped_schedule[cid], condition["roles"], condition_id=cid,
                                   seed=freeze["seeds"]["bootstrap"], resamples=BOOTSTRAP_RESAMPLES)
        require(result["status"] == "COMPLETE", f"Entire condition is incomplete: {cid}; no successful subset will be written")
        require(result["expected_sessions"] == list(range(1, 11)) and set(result["measured_blocks_per_session"].values()) == {6},
                "Analysis session aggregation differs from frozen protocol")
        result.update(workload=condition["workload"], scope=condition["scope"], configurations=condition["configurations"],
                      accounting=accounting[cid])
        summaries.append(result)
    draw_hashes = {c["bootstrap"]["joint_index_draws_sha256"] for c in summaries}
    require(len(draw_hashes) == 1, "Bootstrap session draws are not common across conditions/contrasts/metrics")
    summary = {
        "schema": SCHEMA, "status": "COMPLETE", "run_id": args.run_id, "tier": freeze["tier"],
        "condition_count": len(summaries), "input_sha256": hashes, "analysis_source_sha256": scripts,
        "frozen_source_sha256": freeze["source_hashes"], "backend_commit": freeze["backend_commit"],
        "parameters": {key: freeze[key] for key in ("n", "q", "w", "t", "recursion_dimension", "database_aggregation")},
        "resource_policy": {key: freeze[key] for key in ("cpu_pool", "memory_threshold_bytes", "hard_memory_limit", "resource_policy", "host_isolation")},
        "timing": freeze["timing"], "statistics": freeze["statistics"], "bootstrap_seed": freeze["seeds"]["bootstrap"],
        "common_joint_index_draws_sha256": next(iter(draw_hashes)),
        "figure_condition_map": freeze["figure_condition_map"],
        "conditions": {c["condition_id"]: c for c in summaries},
        "notes": [
            "Latency ratios exceed one when packed retrieval is faster; primary study R_independent is independently tuned.",
            "Capacity-study R_independent is the fixed full-width repeated capacity reference, not an independently tuned per-length optimum.",
            "CPU time is absolute whole-group user plus system time within each timing scope; no CPU ratio is silently substituted.",
            "Preprocessing is directly measured even when excluded from task latency; it is not a difference between scope medians.",
            "Buffer bytes and readback-derived ciphertext counts are not serialized transport bytes or total/peak memory.",
            "Intervals are approximate pointwise session-cluster percentile summaries, not simultaneous or coverage guarantees.",
            "All ten session effects and absolute method medians are retained, including weaker conditions and shared baseline observations.",
        ],
    }
    full, session_table, config_table = tabular_rows(summaries)
    facts = []
    for condition in summaries:
        for baseline in BASELINES:
            stat = condition["ratios"][baseline]
            low, high = stat["CI95"]
            facts.append({"condition_id": condition["condition_id"], "workload": condition["workload"], "scope": condition["scope"],
                          "contrast": baseline + "/P", "estimate": stat["estimate"], "CI95": stat["CI95"],
                          "pointwise_interval_relation_to_one": "above" if low > 1 else "below" if high < 1 else "contains",
                          "estimator": condition["estimator"], "method_roles": condition["method_roles"],
                          "shared_baseline_observations": condition["shared_baseline_observations"],
                          "summary_pointer": f"/conditions/{condition['condition_id']}/ratios/{baseline}", "input_sha256": hashes})
    claim_map = {"schema": "CORE_CLAIM_MAP_V1", "run_id": args.run_id, "status": "COMPLETE",
                 "figure_condition_map": freeze["figure_condition_map"], "condition_facts": facts,
                 "global_speedup": None, "unmeasured_interpolation": None,
                 "claim_boundary": "Condition-specific descriptive comparisons only. Pointwise intervals are not simultaneous guarantees or causal identification."}
    ledger = {"schema": "CORE_FAILURE_LEDGER_V1", "run_id": args.run_id, "formal_status": report["status"],
              "input_sha256": hashes, "physical_status_counts": dict(Counter(row["status"] for row in rows)),
              "phase_status_counts": {phase: dict(Counter(row["status"] for row in rows if row["phase"] == phase)) for phase in ("warmup", "measured")},
              "failure_entries": [{key: row.get(key) for key in (*KEY_FIELDS, "observation_id", "status", "validated", "failure_reasons", "reason")}
                                  for row in rows if row["status"] != "COMPLETE" or row["validated"] is not True],
              "phase_errors": report["phase_errors"], "preservation_errors": report["preservation_errors"],
              "not_started_tasks": report["not_started_tasks"], "stopped_reason": report["stopped_reason"],
              "note": "The formal raw ledger is authoritative. This complete-run summary does not incorporate pilot/tuning failures or replace their preserved ledgers."}
    # All validation and inference precede the exclusive output directory.
    output.mkdir(parents=True, exist_ok=False)
    csv_new(output / "fullprecision.csv", list(full[0]), full)
    csv_new(output / "session_effects.csv", list(session_table[0]), session_table)
    csv_new(output / "configurations_and_buffers.csv", list(config_table[0]), config_table)
    json_new(output / "claim_map.json", claim_map)
    json_new(output / "failure_ledger.json", ledger)
    json_new(output / "summary.json", summary)
    output_hashes = {path.name: sha(path) for path in output.iterdir() if path.is_file()}
    provenance = {"schema": "CORE_ANALYSIS_PROVENANCE_V1", "run_id": args.run_id, "status": "COMPLETE",
                  "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  "input_paths": {key: str(path.relative_to(ROOT)).replace("\\", "/") for key, path in inputs.items()},
                  "input_sha256": hashes, "analysis_source_sha256": scripts, "output_sha256": output_hashes,
                  "bootstrap_draw_sha256": summary["common_joint_index_draws_sha256"],
                  "bootstrap_resamples": BOOTSTRAP_RESAMPLES, "conditions": len(summaries),
                  "fullprecision_rows": len(full), "session_effect_rows": len(session_table),
                  "raw_inputs_modified": False, "native_executions": 0}
    json_new(output / "analysis_provenance.json", provenance)
    print(json.dumps({"status": "COMPLETE", "results": str(output), "conditions": len(summaries),
                      "bootstrap_draw_sha256": summary["common_joint_index_draws_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
