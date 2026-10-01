"""Session-level analysis of the frozen core-rebuild measurement schedule.

SPDX-License-Identifier: GPL-3.0-or-later
This module reads new run observations only. It never runs a benchmark and never
changes raw data. A condition receives estimates only if its entire expected
schedule is present, complete, and validated, including shared baseline rows.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from statistics import median
from typing import Iterable, Mapping

ROLES = ("P", "R_matched", "R_independent")
BASELINES = ROLES[1:]
METRICS = ("task_latency_ns", "cpu_time_ns", "preprocessing_ns", "query_buffer_bytes", "reply_buffer_bytes")
KEY_FIELDS = ("condition_id", "session_id", "block_id", "phase", "config_id")
BOOTSTRAP_RESAMPLES = 10_000


def physical_key(row: Mapping) -> tuple:
    """Identify an actual measurement, not a logical contrast alias."""
    return tuple(row[field] for field in KEY_FIELDS)


def percentile(values: Iterable[float], probability: float) -> float:
    """Linear percentile interpolation at (number of values - 1) * p."""
    ordered = sorted(values)
    if not ordered or not 0 <= probability <= 1:
        raise ValueError("A nonempty sample and probability in [0, 1] are required")
    position = (len(ordered) - 1) * probability
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def session_cluster_bootstrap(session_vectors: Mapping[str, Mapping[str, float]], *, seed: int, resamples: int = BOOTSTRAP_RESAMPLES) -> dict:
    """Jointly resample complete sessions, retaining all contrast correlations.

    Session statistics are sufficient here: recomputing the specified estimator
    after selecting whole sessions gives the same median of session medians.
    The same indices select every metric, rather than bootstrapping contrasts
    or individual blocks independently. Raw blocks remain in the source data.
    """
    sessions = list(session_vectors)
    if not sessions or resamples < 1:
        raise ValueError("At least one session and positive resample count are required")
    metrics = list(session_vectors[sessions[0]])
    if not metrics or any(set(session_vectors[s]) != set(metrics) for s in sessions):
        raise ValueError("Session metric vectors must have identical nonempty fields")
    if any(not math.isfinite(float(v)) for s in sessions for v in session_vectors[s].values()):
        raise ValueError("Session effects must be finite")
    rng = random.Random(seed)
    draws_hash = hashlib.sha256()
    replicates = {metric: [] for metric in metrics}
    for _ in range(resamples):
        indices = [rng.randrange(len(sessions)) for _ in sessions]
        draws_hash.update(json.dumps(indices, separators=(",", ":")).encode("ascii") + b"\n")
        for metric in metrics:
            replicates[metric].append(median(session_vectors[sessions[index]][metric] for index in indices))
    return {
        "unit": "whole_session",
        "seed": seed,
        "resamples": resamples,
        "session_order": sessions,
        "joint_index_draws_sha256": draws_hash.hexdigest(),
        "percentile_rule": "linear interpolation at (resamples - 1) * p",
        "coverage": "pointwise 95% percentile intervals; not simultaneous coverage",
        "CI95": {metric: [percentile(values, .025), percentile(values, .975)] for metric, values in replicates.items()},
        "replicates": replicates,
    }


def analyze_condition(observations: Iterable[Mapping], expected_schedule: Iterable[Mapping], method_roles: Mapping[str, str], *, condition_id: str, seed: int, resamples: int = BOOTSTRAP_RESAMPLES) -> dict:
    """Summarize one condition against its full frozen physical schedule.

    Rows have the five KEY_FIELDS, observation_id, status, validated, and all
    METRICS. method_roles maps the three logical roles to actual config IDs.
    Duplicate baseline configs share one physical row; no duplicate samples are
    created. The expected schedule contains warmup and measured physical tasks.
    Any missing/failed/unvalidated task makes the entire condition incomplete.
    """
    if set(method_roles) != set(ROLES):
        raise ValueError("Exactly P, R_matched and R_independent roles are required")
    if method_roles["P"] in {method_roles[b] for b in BASELINES}:
        raise ValueError("Packed and repeated observations must be distinct tasks")
    rows = [dict(row) for row in observations if row["condition_id"] == condition_id]
    schedule = [dict(row) for row in expected_schedule if row["condition_id"] == condition_id]
    if not schedule:
        raise ValueError("Condition is absent from the frozen expected schedule")
    issues = []
    expected_keys = [physical_key(row) for row in schedule]
    if len(set(expected_keys)) != len(expected_keys):
        raise ValueError("Frozen schedule contains duplicate physical tasks")
    expected_set = set(expected_keys)
    by_key = {}
    seen_ids = set()
    for row in rows:
        key = physical_key(row)
        if key in by_key:
            issues.append({"reason": "duplicate_physical_observation", "key": list(key)})
        else:
            by_key[key] = row
        observation_id = row["observation_id"]
        if observation_id in seen_ids:
            issues.append({"reason": "reused_observation_id", "observation_id": observation_id})
        seen_ids.add(observation_id)
        if key not in expected_set:
            issues.append({"reason": "unexpected_observation", "key": list(key)})
        if row.get("status") != "COMPLETE" or row.get("validated") is not True:
            issues.append({"reason": "failed_or_unvalidated", "key": list(key), "status": row.get("status"), "validated": row.get("validated")})
        else:
            for metric in METRICS:
                value = row.get(metric)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (metric == "task_latency_ns" and value == 0):
                    issues.append({"reason": "invalid_metric", "key": list(key), "metric": metric, "value": value})
    for key in expected_keys:
        if key not in by_key:
            issues.append({"reason": "missing_observation", "key": list(key), "status": "NOT_STARTED"})
    for field in ("run_id", "code_sha256", "build_sha256"):
        values = {row[field] for row in rows if field in row}
        if len(values) > 1:
            issues.append({"reason": "mixed_provenance", "field": field, "values": sorted(values)})
    blocks = defaultdict(set)
    for row in schedule:
        if row["phase"] not in ("warmup", "measured"):
            raise ValueError("Expected schedule must contain only warmup/measured tasks")
        blocks[(row["session_id"], row["block_id"], row["phase"])].add(row["config_id"])
    unique_configs = set(method_roles.values())
    if any(configs != unique_configs for configs in blocks.values()):
        raise ValueError("Every frozen block must contain exactly the physical configs needed by its roles")
    session_order = list(dict.fromkeys(row["session_id"] for row in schedule))
    measured_blocks = {session: list(dict.fromkeys(row["block_id"] for row in schedule if row["session_id"] == session and row["phase"] == "measured")) for session in session_order}
    if any(not ids for ids in measured_blocks.values()):
        raise ValueError("Every expected session must have measured blocks")
    counts = Counter(row.get("status", "MISSING_STATUS") for row in rows)
    output = {
        "condition_id": condition_id,
        "status": "INCOMPLETE" if issues else "COMPLETE",
        "method_roles": dict(method_roles),
        "shared_baseline_observations": method_roles["R_matched"] == method_roles["R_independent"],
        "expected_physical_observations": len(schedule),
        "observed_physical_observations": len(rows),
        "observation_status_counts": dict(counts),
        "expected_sessions": session_order,
        "measured_blocks_per_session": {session: len(ids) for session, ids in measured_blocks.items()},
        "issues": issues,
        "estimator": "median across sessions of within-session median paired baseline/packed ratios",
        "absolute_estimator": "median across sessions of within-session method medians",
    }
    if issues:
        # Preserve status and reasons; do not estimate from a successful subset.
        return output
    sessions = []
    vectors = {}
    for session in session_order:
        role_rows = {role: [by_key[(condition_id, session, block, "measured", config)] for block in measured_blocks[session]] for role, config in method_roles.items()}
        absolute = {role: {metric: median(row[metric] for row in role_rows[role]) for metric in METRICS} for role in ROLES}
        paired_ratios = {baseline: [b["task_latency_ns"] / p["task_latency_ns"] for b, p in zip(role_rows[baseline], role_rows["P"])] for baseline in BASELINES}
        effects = {baseline: median(values) for baseline, values in paired_ratios.items()}
        vectors[session] = {"ratio/" + baseline: effect for baseline, effect in effects.items()}
        vectors[session].update({role + "/" + metric: value for role, metrics in absolute.items() for metric, value in metrics.items()})
        sessions.append({"session_id": session, "paired_block_ids": measured_blocks[session], "ratios": effects, "paired_ratios": paired_ratios, "absolute": absolute, "role_observation_ids": {role: [row["observation_id"] for row in role_rows[role]] for role in ROLES}})
    bootstrap = session_cluster_bootstrap(vectors, seed=seed, resamples=resamples)
    output["sessions"] = sessions
    output["ratios"] = {baseline: {"estimate": median(session["ratios"][baseline] for session in sessions), "CI95": bootstrap["CI95"]["ratio/" + baseline]} for baseline in BASELINES}
    output["absolute"] = {role: {metric: {"estimate": median(session["absolute"][role][metric] for session in sessions), "CI95": bootstrap["CI95"][role + "/" + metric]} for metric in METRICS} for role in ROLES}
    # Replicates are available from the pure bootstrap API for checks. The run
    # summary records the common draw digest and intervals instead of 170k values.
    output["bootstrap"] = {key: value for key, value in bootstrap.items() if key not in ("replicates", "CI95")}
    return output
