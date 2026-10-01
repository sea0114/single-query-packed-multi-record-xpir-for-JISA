"""Linux measurement isolation and explicitly selected resource policies.

SPDX-License-Identifier: GPL-3.0-or-later
Importing this module performs no writes. Cgroup creation requires an explicit
authorization flag; stale locks are reported and never automatically removed.
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
import re
import time
import uuid

DEFAULT_MEMORY_LIMIT = 8 * 1024**3
COMPETING_NAMES = {
    "core_native", "I1_worker", "I2_worker", "b1_run", "execute_b3",
    "nativebench", "native_bench", "benchmark_runner", "execute_b1",
    "gcc", "g++", "cc", "c++", "clang", "clang++", "cc1", "cc1plus",
    "cmake", "make", "ninja", "latex", "pdflatex", "xelatex", "lualatex",
    "latexmk", "pdftoppm", "pdftocairo",
    "pilot", "pilot_refine", "tune", "formal", "functional", "analyze",
}


class MeasurementLockError(RuntimeError):
    def __init__(self, state, record, path):
        self.state, self.record, self.path = state, record, str(path)
        super().__init__(f"Measurement lock {state}: {path}; record={record!r}")


class CompetingProcessesError(RuntimeError):
    def __init__(self, processes):
        self.processes = processes
        super().__init__(f"Competing measurement or heavy-work processes: {processes!r}")


class MemoryLimitExceeded(RuntimeError):
    def __init__(self, record):
        self.record = record
        super().__init__(f"Frozen memory threshold exceeded: {record!r}")


def process_start_ticks(pid, proc_root=Path("/proc")):
    """Read field 22 without assuming the comm field contains no spaces."""
    text = (Path(proc_root) / str(pid) / "stat").read_text()
    return int(text[text.rfind(")") + 2:].split()[19])


def boot_id(proc_root=Path("/proc")):
    return (Path(proc_root) / "sys/kernel/random/boot_id").read_text().strip()


def lock_record_state(record, proc_root=Path("/proc")):
    try:
        if record["boot_id"] != boot_id(proc_root):
            return "stale_different_boot"
        if process_start_ticks(int(record["pid"]), proc_root) != int(record["process_start_ticks"]):
            return "stale_reused_pid"
        return "active"
    except (FileNotFoundError, ProcessLookupError):
        return "stale_process_absent"
    except (KeyError, ValueError, PermissionError, OSError) as error:
        return "unverifiable_" + type(error).__name__


def competing_command(command):
    """Return the detected task name; do not inspect source contents or secrets."""
    for argument in command:
        name = Path(argument).name
        stem = name[:-3] if name.endswith(".py") else name
        if stem in COMPETING_NAMES or stem.startswith(("core_native-", "I1_worker-", "I2_worker-")):
            return stem
    return None


def scan_competing_processes(*, allowed_pids=(), proc_root=Path("/proc")):
    root, allowed = Path(proc_root), {int(pid) for pid in allowed_pids}
    findings = []
    for directory in root.iterdir():
        if not directory.name.isdigit() or int(directory.name) in allowed:
            continue
        try:
            command = [part.decode("utf-8", errors="replace") for part in (directory / "cmdline").read_bytes().split(b"\0") if part]
            detected = competing_command(command)
            if detected:
                # Record only executable/task names, avoiding arbitrary arguments.
                findings.append({"pid": int(directory.name), "process_start_ticks": process_start_ticks(int(directory.name), root), "task": detected, "executable": Path(command[0]).name})
        except (FileNotFoundError, ProcessLookupError):
            continue  # A process that has already exited cannot compete.
        except PermissionError:
            findings.append({"pid": int(directory.name), "task": "unreadable_process", "inspection": "permission_denied"})
    return sorted(findings, key=lambda row: row["pid"])


class MeasurementLock:
    """An atomic project lock plus a scan for legacy jobs that do not use it."""
    def __init__(self, project_root, run_id, *, allowed_pids=(), proc_root=Path("/proc")):
        self.path = Path(project_root).resolve() / "experiments/measurement.lock"
        self.run_id = str(run_id)
        self.proc_root = Path(proc_root)
        self.allowed_pids = {os.getpid(), *map(int, allowed_pids)}
        self.record = None
        self._inode = None

    def acquire(self):
        if self.record is not None:
            raise RuntimeError("This lock instance has already acquired a lock")
        record = {
            "schema_version": 1,
            "pid": os.getpid(),
            "process_start_ticks": process_start_ticks(os.getpid(), self.proc_root),
            "boot_id": boot_id(self.proc_root),
            "run_id": self.run_id,
            "owner_token": uuid.uuid4().hex,
            "acquired_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            try:
                existing = json.loads(self.path.read_text(encoding="utf-8"))
                state = lock_record_state(existing, self.proc_root)
            except (OSError, ValueError) as error:
                existing, state = {"read_error": type(error).__name__}, "unreadable_or_incomplete"
            raise MeasurementLockError(state, existing, self.path)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(record, stream, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
                self._inode = os.fstat(stream.fileno()).st_ino
            self.record = record
            competing = scan_competing_processes(allowed_pids=self.allowed_pids, proc_root=self.proc_root)
            if competing:
                self.release()
                raise CompetingProcessesError(competing)
            return record
        except Exception:
            # A partially written file remains an explicit lock error; never
            # remove a path whose ownership has not been established.
            raise

    def release(self):
        if self.record is None:
            return
        current = json.loads(self.path.read_text(encoding="utf-8"))
        if current != self.record or self.path.stat().st_ino != self._inode:
            raise MeasurementLockError("ownership_changed", current, self.path)
        if os.getpid() != self.record["pid"] or process_start_ticks(os.getpid(), self.proc_root) != self.record["process_start_ticks"]:
            raise MeasurementLockError("not_acquiring_process", current, self.path)
        self.path.unlink()
        self.record = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.release()


def current_cgroup_directory(proc_root=Path("/proc"), cgroup_root=Path("/sys/fs/cgroup")):
    for line in (Path(proc_root) / "self/cgroup").read_text().splitlines():
        if line.startswith("0::"):
            relative = line[3:].lstrip("/")
            root = Path(cgroup_root).resolve()
            directory = (root / relative).resolve()
            if not directory.is_relative_to(root):
                raise ValueError("Invalid cgroup membership path")
            return directory
    return None


def probe_group_resources(*, proc_root=Path("/proc"), cgroup_root=Path("/sys/fs/cgroup")):
    """Read-only preflight; writable paths are hints, not hard-limit acceptance."""
    if not hasattr(os, "sched_getaffinity"):
        return {"platform": os.name, "linux_affinity": False, "cgroup_v2": False, "hard_limit_verified": False}
    current = current_cgroup_directory(proc_root, cgroup_root)
    root = Path(cgroup_root)
    controllers = (root / "cgroup.controllers").read_text().split() if (root / "cgroup.controllers").exists() else []
    return {
        "platform": os.name,
        "linux_affinity": True,
        "available_cpu_ids": sorted(os.sched_getaffinity(0)),
        "cgroup_v2": current is not None,
        "current_cgroup": str(current) if current else None,
        "controllers": controllers,
        "current_subtree_control": (current / "cgroup.subtree_control").read_text().split() if current and (current / "cgroup.subtree_control").exists() else [],
        "can_request_child_cgroup": bool(current and os.access(current, os.W_OK)),
        "memory_controller_present": "memory" in controllers,
        "hard_limit_verified": False,
        "note": "A write/readback preflight is required before freezing a cgroup hard-limit policy",
    }


def parse_smaps(text, *, shared_identity=None):
    """Separate known DB mappings so their pages are counted once by the group.

    shared_identity is (major-device, minor-device, inode), from fstat(shared_fd).
    PSS is proportional resident memory, not an exact instantaneous group peak.
    """
    mappings, current = [], None
    for line in text.splitlines():
        if re.match(r"^[0-9a-f]+-[0-9a-f]+\s", line):
            if current is not None:
                mappings.append(current)
            fields = line.split(maxsplit=5)
            major, minor = fields[3].split(":")
            identity = (int(major, 16), int(minor, 16), int(fields[4]))
            current = {"is_database": shared_identity is not None and identity == tuple(shared_identity), "fields": {}}
        elif current is not None:
            match = re.match(r"^(Rss|Pss|Private_Clean|Private_Dirty|Private_Hugetlb):\s+(\d+)\s+kB$", line)
            if match:
                current["fields"][match[1]] = int(match[2]) * 1024
    if current is not None:
        mappings.append(current)
    total = {"rss_bytes": 0, "pss_bytes": 0, "private_bytes": 0, "private_non_db_bytes": 0, "non_db_shared_pss_bytes": 0, "database_pss_bytes": 0}
    for mapping in mappings:
        fields = mapping["fields"]
        private = sum(fields.get(field, 0) for field in ("Private_Clean", "Private_Dirty", "Private_Hugetlb"))
        pss = fields.get("Pss", 0)
        total["rss_bytes"] += fields.get("Rss", 0)
        total["pss_bytes"] += pss
        total["private_bytes"] += private
        if mapping["is_database"]:
            total["database_pss_bytes"] += pss
        else:
            total["private_non_db_bytes"] += private
            total["non_db_shared_pss_bytes"] += max(0, pss - private)
    total["mapping_count"] = len(mappings)
    return total


def shared_fd_identity(fd):
    stat = os.fstat(fd)
    return os.major(stat.st_dev), os.minor(stat.st_dev), stat.st_ino


def memory_threshold_exceeded(estimated_bytes, limit_bytes):
    """The monitored policy aborts only when the frozen threshold is exceeded."""
    return int(estimated_bytes) > int(limit_bytes)


class GroupResources:
    """Apply affinity to the coordinator and inherited child tasks.

    policy='monitor' uses a frozen sampled-abort threshold, not a kernel hard
    limit. policy='cgroup' requires prior authorization and readback acceptance;
    its CPU counters retain CPU time of exited child processes.
    """
    def __init__(self, cpu_pool, *, run_id, memory_limit_bytes=DEFAULT_MEMORY_LIMIT, memory_policy="monitor", authorize_cgroup_write=False, cgroup_parent=None, proc_root=Path("/proc")):
        self.cpu_pool = set(map(int, cpu_pool))
        self.run_id = str(run_id)
        self.memory_limit_bytes = int(memory_limit_bytes)
        self.memory_policy = memory_policy
        self.authorize_cgroup_write = authorize_cgroup_write
        self.cgroup_parent = Path(cgroup_parent) if cgroup_parent else None
        self.proc_root = Path(proc_root)
        self.cgroup_path = None
        self.original_affinity = None
        if memory_policy not in ("monitor", "cgroup") or not self.cpu_pool or self.memory_limit_bytes <= 0:
            raise ValueError("Specify a nonempty CPU pool, positive memory limit and frozen policy")

    def __enter__(self):
        self.original_affinity = set(os.sched_getaffinity(0))
        if not self.cpu_pool <= self.original_affinity:
            raise ValueError("Selected CPUs are outside the available affinity set")
        if self.memory_policy == "cgroup":
            if not self.authorize_cgroup_write:
                raise PermissionError("Cgroup writes require explicit preflight authorization")
            parent = self.cgroup_parent or current_cgroup_directory(self.proc_root)
            if parent is None:
                raise RuntimeError("Cgroup v2 is unavailable; do not silently change the frozen policy")
            safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", self.run_id)[:60]
            child = parent / ("core-rebuild-" + safe_id + "-" + str(os.getpid()) + "-" + uuid.uuid4().hex[:8])
            child.mkdir()  # A new, uniquely owned group; never reuse another run.
            self.cgroup_parent, self.cgroup_path = parent, child
            try:
                (child / "memory.max").write_text(str(self.memory_limit_bytes))
                if int((child / "memory.max").read_text()) != self.memory_limit_bytes:
                    raise RuntimeError("Cgroup memory.max readback mismatch")
                if (child / "memory.swap.max").exists():
                    (child / "memory.swap.max").write_text("0")
                    if (child / "memory.swap.max").read_text().strip() != "0":
                        raise RuntimeError("Cgroup swap policy readback mismatch")
                (child / "cgroup.procs").write_text(str(os.getpid()))
            except Exception:
                # Only a newly created empty group may be removed. Never relax
                # limits or move unrelated processes to make creation succeed.
                if not (child / "cgroup.procs").read_text().strip():
                    child.rmdir()
                    self.cgroup_path = None
                raise
        try:
            os.sched_setaffinity(0, self.cpu_pool)
        except Exception:
            if self.cgroup_path is not None:
                self._release_cgroup()
            raise
        return self

    def _release_cgroup(self):
        members = {int(value) for value in (self.cgroup_path / "cgroup.procs").read_text().split()}
        if members - {os.getpid()}:
            raise RuntimeError("Resource group still has live children; caller must finish its own tasks before release")
        if os.getpid() in members:
            (self.cgroup_parent / "cgroup.procs").write_text(str(os.getpid()))
        self.cgroup_path.rmdir()
        self.cgroup_path = None

    def cpu_snapshot(self):
        if self.cgroup_path is None:
            return {"source": "unavailable", "note": "Use coordinator/child rusage deltas in the runner; do not infer exited-child CPU from /proc"}
        counters = {}
        for line in (self.cgroup_path / "cpu.stat").read_text().splitlines():
            name, value = line.split()
            counters[name] = int(value)
        return {"source": "cgroup_v2_cpu.stat", "counters": counters, "user_ns": counters.get("user_usec", 0) * 1000, "system_ns": counters.get("system_usec", 0) * 1000}

    def monitor(self, pids, *, shared_bytes=0, shared_identity=None):
        records, unavailable = [], []
        for pid in sorted({os.getpid(), *map(int, pids)}):
            try:
                record = parse_smaps((self.proc_root / str(pid) / "smaps").read_text(), shared_identity=shared_identity)
                record.update(pid=pid, process_start_ticks=process_start_ticks(pid, self.proc_root))
                records.append(record)
            except (FileNotFoundError, ProcessLookupError):
                unavailable.append({"pid": pid, "state": "exited_before_sample"})
            except PermissionError:
                unavailable.append({"pid": pid, "state": "permission_denied"})
        if shared_bytes and shared_identity is None:
            raise ValueError("Supply the shared memfd identity to avoid double-counting DB mappings")
        private = sum(row["private_non_db_bytes"] for row in records)
        other_shared = sum(row["non_db_shared_pss_bytes"] for row in records)
        estimate = private + other_shared + int(shared_bytes)
        record = {
            "monotonic_ns": time.monotonic_ns(), "policy": self.memory_policy,
            "limit_bytes": self.memory_limit_bytes,
            "processes": records, "unavailable_processes": unavailable,
            "private_non_db_bytes": private, "non_db_shared_pss_bytes": other_shared,
            "unique_database_storage_bytes": int(shared_bytes),
            "estimated_memory_bytes": estimate,
            "interpretation": "Sampled private resident memory plus proportional non-DB shared memory and unique DB storage; not exact group peak memory",
            "above_threshold": memory_threshold_exceeded(estimate, self.memory_limit_bytes),
        }
        if self.cgroup_path is not None:
            record["cgroup_memory_current_bytes"] = int((self.cgroup_path / "memory.current").read_text())
            record["cgroup_memory_events"] = dict(line.split() for line in (self.cgroup_path / "memory.events").read_text().splitlines())
        elif any(row["state"] == "permission_denied" for row in unavailable):
            raise RuntimeError("Cannot enforce the frozen monitoring policy with unreadable active processes")
        if self.memory_policy == "monitor" and record["above_threshold"]:
            raise MemoryLimitExceeded(record)
        return record

    def __exit__(self, exc_type, exc, traceback):
        try:
            if self.cgroup_path is not None:
                self._release_cgroup()
        finally:
            if self.original_affinity is not None:
                os.sched_setaffinity(0, self.original_affinity)
