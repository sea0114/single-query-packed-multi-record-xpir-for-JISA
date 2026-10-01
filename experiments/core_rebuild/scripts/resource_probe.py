#!/usr/bin/env python3
"""Pre-freeze resource-policy probe, without native execution or benchmarks.

SPDX-License-Identifier: GPL-3.0-or-later
Only an explicit --authorize-cgroup-write permits a new, uniquely owned Linux
cgroup. The resulting provenance is written exclusively under the selected run.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import platform

from common import CORE, ROOT, MEMORY_LIMIT, sha, write_new
from resources import (GroupResources, MeasurementLock, probe_group_resources,
                       memory_threshold_exceeded)


def read_optional(path):
    try:
        return Path(path).read_text().strip()
    except (OSError, ValueError):
        return None


def select_cpu_pool(available, *, count=4, topology_root=Path("/sys/devices/system/cpu")):
    """Prefer separate guest-reported physical core IDs, then fill with siblings."""
    rows = []
    for cpu in sorted(available):
        root = Path(topology_root) / f"cpu{cpu}"
        package = read_optional(root / "topology/physical_package_id")
        core = read_optional(root / "topology/core_id")
        rows.append({"cpu_id": cpu, "physical_package_id": package,
                     "core_id": core,
                     "thread_siblings_list": read_optional(root / "topology/thread_siblings_list"),
                     "scaling_governor": read_optional(root / "cpufreq/scaling_governor"),
                     "scaling_cur_freq_khz": read_optional(root / "cpufreq/scaling_cur_freq"),
                     "scaling_max_freq_khz": read_optional(root / "cpufreq/scaling_max_freq")})
    if len(rows) < count:
        raise ValueError(f"Need {count} available CPU positions; found {len(rows)}")
    selected, identities = [], set()
    for row in rows:
        identity = (row["physical_package_id"], row["core_id"])
        if None in identity:
            identity = ("unknown", row["cpu_id"])
        if identity not in identities:
            selected.append(row["cpu_id"])
            identities.add(identity)
            if len(selected) == count:
                break
    for row in rows:
        if len(selected) == count:
            break
        if row["cpu_id"] not in selected:
            selected.append(row["cpu_id"])
    return selected, rows


def context_probe(cpu_pool, run_id, *, policy, authorize_cgroup_write=False, parent=None):
    context = GroupResources(cpu_pool, run_id=run_id + "-resource-probe",
                             memory_limit_bytes=MEMORY_LIMIT,
                             memory_policy=policy,
                             authorize_cgroup_write=authorize_cgroup_write,
                             cgroup_parent=parent)
    original_affinity = sorted(os.sched_getaffinity(0))
    result = {"policy": policy, "status": "NOT_STARTED", "cleanup": "NOT_STARTED"}
    created_path = None
    try:
        with context:
            created_path = context.cgroup_path
            result["status"] = "COMPLETE"
            result["affinity_readback"] = sorted(os.sched_getaffinity(0))
            if result["affinity_readback"] != sorted(cpu_pool):
                raise RuntimeError("CPU assignment readback mismatch")
            if created_path is not None:
                result["cgroup_path"] = str(created_path)
                result["memory_max_readback_bytes"] = int((created_path / "memory.max").read_text())
                result["memory_swap_max_readback"] = read_optional(created_path / "memory.swap.max")
            result["cpu_snapshot"] = context.cpu_snapshot()
            result["monitor_snapshot"] = context.monitor([])
    except Exception as error:
        result["status"] = "FAILED"
        result["error_type"] = type(error).__name__
        result["error"] = str(error)
        if context.cgroup_path is not None:
            created_path = context.cgroup_path
            result["cgroup_path"] = str(created_path)
            try:
                # Release only this new context's group and acquiring process.
                context.__exit__(type(error), error, error.__traceback__)
            except Exception as cleanup_error:
                result["cleanup_error_type"] = type(cleanup_error).__name__
                result["cleanup_error"] = str(cleanup_error)
    result["affinity_restored"] = sorted(os.sched_getaffinity(0)) == original_affinity
    result["owned_cgroup_removed"] = created_path is None or not created_path.exists()
    result["cleanup"] = "COMPLETE" if result["affinity_restored"] and result["owned_cgroup_removed"] else "FAILED"
    result["over_limit_allocation_tested"] = False
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--authorize-cgroup-write", action="store_true")
    args = parser.parse_args()
    run = args.run_dir.resolve()
    if not run.is_relative_to((CORE / "runs").resolve()) or run == (CORE / "runs").resolve():
        raise ValueError("Select one run directory under experiments/core_rebuild/runs")
    output = run / "provenance/resource_probe.json"
    if output.exists():
        raise FileExistsError(f"Resource provenance already exists: {output}")
    report = {
        "schema_version": 1, "run_id": run.name,
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "NOT_STARTED", "platform": platform.platform(),
        "kernel_release": platform.release(),
        "wsl_guest": "microsoft" in platform.release().lower(),
        "memory_limit_bytes": MEMORY_LIMIT,
        "cgroup_write_authorized": args.authorize_cgroup_write,
        "script_sha256": {name: sha(Path(__file__).with_name(name)) for name in ("resource_probe.py", "resources.py", "common.py")},
        "new_measurements": 0, "native_executions": 0, "compilation": False,
        "host_isolation_note": "Guest affinity/topology does not establish exclusive Windows-host CPU or memory isolation",
    }
    try:
        if os.name != "posix" or not hasattr(os, "sched_getaffinity"):
            raise RuntimeError("Run this resource probe in the Linux/WSL experiment environment")
        with MeasurementLock(ROOT, run.name + "-resource-probe") as lock:
            report["measurement_lock"] = dict(lock.record)
            report["read_only_probe"] = probe_group_resources()
            cpu_pool, topology = select_cpu_pool(report["read_only_probe"]["available_cpu_ids"])
            report["cpu_pool"], report["cpu_topology"] = cpu_pool, topology
            if args.authorize_cgroup_write:
                hard = context_probe(cpu_pool, run.name, policy="cgroup",
                                     authorize_cgroup_write=True,
                                     parent=report["read_only_probe"]["current_cgroup"])
            else:
                hard = {"policy": "cgroup", "status": "NOT_ATTEMPTED", "reason": "No explicit cgroup-write authorization", "cleanup": "COMPLETE"}
            report["cgroup_attempt"] = hard
            if hard["cleanup"] != "COMPLETE":
                raise RuntimeError("The owned hard-limit probe did not clean up; no fallback accepted")
            if hard["status"] == "COMPLETE":
                report["memory_policy"] = "cgroup"
                report["hard_limit_configured_readback"] = hard["memory_max_readback_bytes"] == MEMORY_LIMIT
                report["hard_limit_verified"] = report["hard_limit_configured_readback"]
                if not report["hard_limit_verified"]:
                    raise RuntimeError("Hard-limit readback failed")
            else:
                monitor = context_probe(cpu_pool, run.name, policy="monitor")
                report["monitor_attempt"] = monitor
                if monitor["status"] != "COMPLETE" or monitor["cleanup"] != "COMPLETE":
                    raise RuntimeError("Consistent monitoring policy could not be accepted")
                report["memory_policy"] = "monitor"
                report["hard_limit_verified"] = False
                report["monitoring_policy_note"] = "Pre-freeze fallback: sampled abort threshold, not an OS memory hard limit or exact peak-memory measurement"
            assert not memory_threshold_exceeded(MEMORY_LIMIT - 1, MEMORY_LIMIT)
            assert not memory_threshold_exceeded(MEMORY_LIMIT, MEMORY_LIMIT)
            assert memory_threshold_exceeded(MEMORY_LIMIT + 1, MEMORY_LIMIT)
            report["synthetic_threshold_boundary_check"] = "PASS"
            report["status"] = "COMPLETE"
        report["measurement_lock_released"] = lock.record is None
    except Exception as error:
        report["status"] = "FAILED"
        report["error_type"], report["error"] = type(error).__name__, str(error)
        if hasattr(error, "record"):
            report["blocking_record"] = error.record
        if hasattr(error, "processes"):
            report["competing_processes"] = error.processes
    write_new(output, report)
    print(json.dumps({"status": report["status"], "provenance": str(output), "cpu_pool": report.get("cpu_pool"), "memory_policy": report.get("memory_policy"), "hard_limit_verified": report.get("hard_limit_verified", False)}))
    return 0 if report["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
