"""Synthetic-only B3 runner tests: never launch native binaries or benchmark.

The process protocol, timestamps, and resource counters below are deliberately
fabricated unit-test fixtures. They must never enter artifact/raw or performance
analysis. Tests run on Windows or Linux using an entirely mocked process layer.
"""
import contextlib
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "artifact/scripts"))
try:
    import resource
except ImportError:
    resource = types.ModuleType("resource")
    for index, name in enumerate(("RUSAGE_SELF", "RLIMIT_AS", "RLIMIT_FSIZE", "RLIMIT_CORE")):
        setattr(resource, name, index)
    resource.getrusage = lambda _: types.SimpleNamespace(ru_utime=0, ru_stime=0, ru_maxrss=0)
    resource.setrlimit = lambda *args: None
    sys.modules["resource"] = resource
common = importlib.import_module("b3_common")
runner = importlib.import_module("b3_runner")


class SyntheticProtocol:
    """In-memory R/D/V protocol with temporary, synthetic JSON result files."""
    def __init__(self, *, method="repeated", policy="R2", alpha=2, ell=512, view="COLD",
                 worker_transform=None, spawn_fail_at=None, aggregate_vm_kib=100,
                 hard_deadline=None, exit_before_barrier=False, trace_budget_bytes=None):
        self.method, self.policy = method, policy
        self.cell = {"study": "SYNTHETIC_UNIT_TEST_ONLY", "cell_id": "SYNTHETIC_NEVER_BENCHMARK",
                     "implementation_id": "I2", "resource_policy_id": policy, "view": view,
                     **common.point(alpha, 8, ell)}
        self.entry = {"method": method, "pair_id": "SYNTHETIC_PAIR", "session_id": "UNIT_TEST"}
        self.worker_transform = worker_transform
        self.spawn_fail_at = spawn_fail_at
        self.aggregate_vm_kib = aggregate_vm_kib
        self.hard_deadline = hard_deadline
        self.exit_before_barrier = exit_before_barrier
        self.trace_budget_bytes = trace_budget_bytes
        self.caps = dict(common.CAPS)
        self.processes, self.fd_queues, self.fd_owner = [], {}, {}
        self.events, self.limits, self.closed = [], [], []
        self.next_fd, self.clock = 1000, 10_000
        self.temp = tempfile.TemporaryDirectory(prefix="b3-synthetic-unit-test-")
        self.root = Path(self.temp.name)
        self.out = self.root / "run"
        self.binary = self.root / "FAKE_NOT_A_NATIVE_BINARY"
        self.binary.write_text("SYNTHETIC UNIT TEST ONLY", encoding="utf-8")
        self.original_read_text = Path.read_text

    def cleanup(self):
        self.temp.cleanup()

    def now(self):
        self.clock += 100
        return self.clock

    def pipe(self):
        fd = self.next_fd
        self.next_fd += 2
        return fd, fd + 1

    def read(self, fd, count):
        value = self.fd_queues[fd].pop(0)
        self.events.append(("read", self.fd_owner[fd], value))
        return value

    def write(self, fd, data):
        proc = next(p for p in self.processes if p.go_write_fd == fd)
        if len(data) == 8:
            proc.released = True
            self.events.append(("release", proc.index))
            self.fd_queues[proc.ready_read_fd].append(b"D")
        elif data == b"V":
            done_seen = {event[1] for event in self.events if event[0] == "read" and event[2] == b"D"}
            if len(done_seen) != len(self.processes):
                raise AssertionError("Validation released before all workers sent DONE")
            self.events.append(("validate", proc.index))
            proc.finished = True
        else:
            raise AssertionError("Unknown synthetic protocol message")
        return len(data)

    def select(self, fds, *args):
        # Deliberately expose one worker at a time to exercise barrier joins.
        available = [fd for fd in fds if self.fd_queues.get(fd)]
        return available[:1], [], []

    def result(self, job, index):
        start, end = 1000 + index * 10, 1200 + index * 100
        phase_events = {}
        for name in common.PHASES:
            begin = 2000 if name == "ValidationOverhead" else start + 1
            if self.cell["view"] == "ONLINE" and name in ("ConfigureServer", "EncodeDB", "ImportPreprocess"):
                begin = 100
            phase_events[name] = {"begin": begin, "end": begin + 1}
        policy = common.POLICIES[self.policy]
        affinity = policy["packed_affinity"] if self.method == "packed" else policy["repeated_affinity"][index]
        value = {
            "status": "COMPLETE", "failure_reason": "", "output_verified": True,
            "cpu_affinity": affinity, "actual_hex": [common.fixture(8, self.cell["ell_bits"])[t].hex() for t in job["targets"]],
            "db_fixture_hash": self.cell["db_fixture_hash"], "encoded_db_hash": self.cell["encoded_db_hash"],
            "task_start_ns": start, "task_end_ns": end, "task_total_ns": end-start,
            "key_generation_calls": 1, "query_encrypt_calls": 8, "rng_calls": 18,
            "omp_max_threads": 1, "validation_release_seen": True,
            "query_ciphertexts": 8, "reply_ciphertexts": self.cell["L"],
            "query_payload_bytes": 8*common.CT, "reply_payload_bytes": self.cell["L"]*common.CT,
            "all_coefficients_exact": True, "all_segments_exact": True, "padding_exact": True,
            "phase_events": phase_events, "phase_ns": {name: 1 for name in common.PHASES},
            "cpu_user_ns": 10 + index, "cpu_system_ns": 20 + index,
            "key_fingerprint": hashlib.sha256(f"SYNTHETIC_PUBLIC_TEST_TAG_{index}".encode()).hexdigest(),
            "implementation_id": "B3-I2", "variant_label": "RECONSTRUCTED_SOURCE_VARIANT",
            "fixture_id": "pseudorandom-B3-common-seed-8c3f47282900cee8-v1",
            "timing_label": "B3_PILOT", "N": 8, "ell_bits": self.cell["ell_bits"],
            "alpha": self.cell["alpha"], "rho_0": 8, "w": self.cell["w"],
            "J": self.cell["J"], "L": self.cell["L"],
        }
        if self.worker_transform:
            self.worker_transform(value, index)
        return value

    def popen(self, argv, **kwargs):
        index = len(self.processes)
        if self.spawn_fail_at == index:
            raise OSError("Synthetic intentional spawn failure")
        kwargs["preexec_fn"]()
        job = json.loads(Path(argv[1]).read_text())
        p = types.SimpleNamespace(pid=40000 + index, returncode=None, index=index,
                                  ready_read_fd=job["ready_fd"]-1, go_write_fd=job["go_fd"]+1,
                                  released=False, finished=self.exit_before_barrier, reaped=False)
        self.fd_queues[p.ready_read_fd] = [b"R"]
        self.fd_owner[p.ready_read_fd] = index
        self.processes.append(p)
        Path(argv[2]).write_text(json.dumps(self.result(job, index)), encoding="utf-8")
        if self.trace_budget_bytes is not None:
            self.caps["task_disk_bytes"] = sum(f.stat().st_size for f in self.out.iterdir()) + 2*2**20 + self.trace_budget_bytes
        self.events.append(("spawn", index))
        return p

    def wait4(self, pid, flags):
        p = next(p for p in self.processes if p.pid == pid)
        if not p.finished:
            return 0, 0, None
        p.reaped = True
        usage = types.SimpleNamespace(ru_maxrss=100+int(p.index), ru_utime=0.01, ru_stime=0.02)
        return pid, 0, usage

    def killpg(self, pid, sig):
        p = next(p for p in self.processes if p.pid == pid)
        p.finished = True
        self.events.append(("kill", p.index))

    def write_new(self, path, value):
        path = Path(path)
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise AssertionError("Synthetic fixtures escaped temporary test directory")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            stream.write(value if isinstance(value, str) else json.dumps(value))

    def execute(self):
        def text(path, *args, **kwargs):
            if str(path).replace("\\", "/") == "/proc/sys/kernel/random/boot_id":
                return "SYNTHETIC-BOOT-ID"
            return self.original_read_text(path, *args, **kwargs)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(runner, "now", self.now))
            stack.enter_context(mock.patch.object(runner, "write_new", self.write_new))
            stack.enter_context(mock.patch.object(runner, "sample", lambda pid: {"VmRSS": 1, "VmSize": self.aggregate_vm_kib, "Threads": 1}))
            stack.enter_context(mock.patch.object(runner.shutil, "disk_usage", lambda _: types.SimpleNamespace(free=10**15)))
            stack.enter_context(mock.patch.object(runner.os, "sched_getaffinity", lambda _: {0,2,4,6}, create=True))
            stack.enter_context(mock.patch.object(runner.os, "sched_setaffinity", lambda pid, cpus: self.events.append(("affinity", list(cpus))), create=True))
            stack.enter_context(mock.patch.object(runner.resource, "setrlimit", lambda kind, limit: self.limits.append((kind, limit))))
            stack.enter_context(mock.patch.object(runner.resource, "getrusage", lambda _: types.SimpleNamespace(ru_utime=0, ru_stime=0, ru_maxrss=0)))
            stack.enter_context(mock.patch.object(runner.os, "pipe", self.pipe))
            stack.enter_context(mock.patch.object(runner.os, "read", self.read))
            stack.enter_context(mock.patch.object(runner.os, "write", self.write))
            stack.enter_context(mock.patch.object(runner.os, "close", lambda fd: self.closed.append(fd)))
            stack.enter_context(mock.patch.object(runner.os, "killpg", self.killpg, create=True))
            stack.enter_context(mock.patch.object(runner.os, "wait4", self.wait4, create=True))
            stack.enter_context(mock.patch.object(runner.os, "waitstatus_to_exitcode", lambda status: status, create=True))
            stack.enter_context(mock.patch.object(runner.os, "WNOHANG", 1, create=True))
            stack.enter_context(mock.patch.object(runner.signal, "SIGKILL", 9, create=True))
            stack.enter_context(mock.patch.object(runner.select, "select", self.select))
            stack.enter_context(mock.patch.object(runner.time, "sleep", lambda _: None))
            stack.enter_context(mock.patch.object(runner.subprocess, "Popen", self.popen))
            stack.enter_context(mock.patch.object(Path, "read_text", text))
            return runner.run_task(self.cell, self.entry, self.binary, self.out,
                                   label="B3_PILOT", hard_deadline=self.hard_deadline, caps=self.caps)


class CommonContractTests(unittest.TestCase):
    def test_fixture_matches_all_twelve_pinned_B2B_points(self):
        manifest = json.loads((ROOT / "revision_notes/B2_B_freeze_manifest.json").read_text(encoding="utf-8-sig"))
        for historical in manifest["workloads"]:
            with self.subTest(point=historical["point_id"]):
                p = common.point(historical["alpha"], historical["N"], historical["ell_bits"])
                for key in ("db_fixture_hash", "encoded_db_hash", "J", "L", "w", "target_tuple"):
                    self.assertEqual(p[key], historical[key])

    def test_non_byte_aligned_fixture_masks_high_bits(self):
        for ell in (257, 32767, 32769):
            rows = common.fixture(8, ell)
            self.assertEqual(len(rows), 8)
            self.assertTrue(all(len(r) == (ell+7)//8 for r in rows))
            self.assertTrue(all(r[-1] < (1 << (ell % 8)) for r in rows))

    def test_policy_bundles(self):
        p, q = common.POLICIES["R1"], common.POLICIES["R2"]
        self.assertEqual((p["packed_affinity"], p["packed_as_bytes"], p["enforce_aggregate_vm"]), ([0,2],16*2**30,False))
        self.assertEqual((q["packed_affinity"], q["packed_as_bytes"], q["enforce_aggregate_vm"]), ([0],8*2**30,True))
        self.assertEqual(p["repeated_affinity"], [[0],[2]])
        self.assertEqual(q["repeated_affinity"], [[0],[2],[4],[6]])

    def test_preserve_numeric_looking_fingerprints_and_hex(self):
        result = common.normalize({"key_fingerprint":"012345", "actual_hex":["001234"],
                                   "task_total_ns":"100", "output_verified":"true"})
        self.assertEqual(result, {"key_fingerprint":"012345", "actual_hex":["001234"],
                                  "task_total_ns":100, "output_verified":True})


class RunnerProtocolTests(unittest.TestCase):
    def run_protocol(self, **kwargs):
        protocol = SyntheticProtocol(**kwargs)
        self.addCleanup(protocol.cleanup)
        task, workers = protocol.execute()
        return protocol, task, workers

    def test_repeated_endpoint_span_cpu_and_payload_sums(self):
        _, task, workers = self.run_protocol()
        self.assertEqual(task["status"], "COMPLETE")
        self.assertEqual(task["task_total_ns"], 1300-1000)
        self.assertNotEqual(task["task_total_ns"], sum(w["task_total_ns"] for w in workers))
        self.assertEqual((task["cpu_user_ns"], task["cpu_system_ns"]), (21,41))
        self.assertEqual((task["query_ciphertexts"], task["reply_ciphertexts"]), (16,2))
        self.assertEqual(task["worker_lifetime_peak_rss_sum_kib"], 201)
        self.assertIn("not synchronized", task["rss_semantics"])
        self.assertIn("not concurrent critical-path", task["phase_semantics"])

    def test_validation_release_waits_for_every_done(self):
        p, task, _ = self.run_protocol(alpha=4)
        last_done = max(i for i,e in enumerate(p.events) if e[0] == "read" and e[2] == b"D")
        first_validation = min(i for i,e in enumerate(p.events) if e[0] == "validate")
        self.assertGreater(first_validation, last_done)
        self.assertIsNotNone(task["validation_release_ns"])

    def test_early_zero_exit_cannot_skip_parent_barriers(self):
        _, task, _ = self.run_protocol(exit_before_barrier=True)
        self.assertNotEqual(task["status"], "COMPLETE")
        self.assertFalse(task["validation_passed"])

    def test_packed_r1_resources(self):
        p, task, _ = self.run_protocol(method="packed", policy="R1")
        self.assertEqual(task["status"], "COMPLETE")
        self.assertIn((resource.RLIMIT_AS, (16*2**30,)*2), p.limits)
        self.assertIn(("affinity", [0,2]), p.events)

    def test_packed_r2_resources(self):
        p, task, _ = self.run_protocol(method="packed", policy="R2")
        self.assertEqual(task["status"], "COMPLETE")
        self.assertIn((resource.RLIMIT_AS, (8*2**30,)*2), p.limits)
        self.assertIn(("affinity", [0]), p.events)

    def test_aggregate_vm_cap_is_r2_only_and_failure_wins(self):
        for policy, expected in (("R1","COMPLETE"), ("R2","RESOURCE_LIMIT")):
            with self.subTest(policy=policy):
                _, task, workers = self.run_protocol(policy=policy, aggregate_vm_kib=20*2**20)
                self.assertEqual(task["status"], expected)
                if expected != "COMPLETE":
                    self.assertTrue(all(w["status"] == expected and not w["output_verified"] for w in workers))

    def test_buffered_trace_counts_toward_disk_cap_and_is_preserved(self):
        p, task, _ = self.run_protocol(trace_budget_bytes=1)
        self.assertEqual(task["status"], "RESOURCE_LIMIT")
        self.assertIn("buffered trace", task["failure_reason"])
        trace = (p.out / "monitor_samples.jsonl").read_text()
        self.assertEqual(len(trace.splitlines()), task["monitor_samples"])
        self.assertGreater(len(trace.encode()), 1)

    def test_partial_spawn_reaps_started_worker(self):
        p, task, workers = self.run_protocol(spawn_fail_at=1)
        self.assertEqual(task["status"], "RUNTIME_FAIL")
        self.assertEqual(len(workers), 1)
        self.assertTrue(all(child.reaped for child in p.processes))
        self.assertIn(("kill", 0), p.events)
        self.assertEqual(set(p.closed), set(range(1000,1008)))

    def test_expired_global_deadline_launches_no_worker(self):
        p, task, _ = self.run_protocol(hard_deadline=1)
        self.assertEqual(task["status"], "TIMEOUT")
        self.assertEqual(p.processes, [])

    def test_two_block_reply_counts_for_packed_and_repeated(self):
        for method, expected in (("packed",2),("repeated",8)):
            with self.subTest(method=method):
                _, task, _ = self.run_protocol(method=method, alpha=4, ell=65536)
                self.assertEqual(task["status"], "COMPLETE")
                self.assertEqual(task["reply_ciphertexts"], expected)
                self.assertEqual(task["reply_payload_bytes"], expected*common.CT)

    def test_authoritative_worker_metadata_is_not_overwritten(self):
        _, task, workers = self.run_protocol()
        self.assertEqual(task["status"], "COMPLETE")
        for w in workers:
            self.assertEqual(w["implementation_id"], task["implementation_id"])
            self.assertEqual(w["fixture_id"], task["fixture_id"])

    def test_wrong_native_variant_is_rejected(self):
        def wrong_variant(w, _):
            w["implementation_id"] = "B3-I1"
        _, task, _ = self.run_protocol(worker_transform=wrong_variant)
        self.assertEqual(task["status"], "WRONG_OUTPUT")

    def test_wrong_native_parameters_cannot_hide_behind_base_metadata(self):
        def wrong_parameters(w, _):
            w["N"] = 9
        _, task, _ = self.run_protocol(worker_transform=wrong_parameters)
        self.assertEqual(task["status"], "WRONG_OUTPUT")

    def test_wrong_native_fixture_hash_cannot_hide_behind_base_metadata(self):
        for field in ("db_fixture_hash", "encoded_db_hash"):
            with self.subTest(field=field):
                def wrong_hash(w, _):
                    w[field] = "f"*64
                _, task, _ = self.run_protocol(worker_transform=wrong_hash)
                self.assertEqual(task["status"], "WRONG_OUTPUT")

    def test_duplicate_fingerprint_rejects_whole_task(self):
        def duplicate_key(w, _):
            w["key_fingerprint"] = "a"*64
        _, task, _ = self.run_protocol(worker_transform=duplicate_key)
        self.assertEqual(task["status"], "RUNTIME_FAIL")

    def test_online_staging_must_end_before_task_start(self):
        _, task, _ = self.run_protocol(view="ONLINE")
        self.assertEqual(task["status"], "COMPLETE")
        def invalid_staging(w, _):
            start = w["task_start_ns"]
            w["phase_events"]["ConfigureServer"] = {"begin":start+1, "end":start+2}
        _, task, _ = self.run_protocol(view="ONLINE", worker_transform=invalid_staging)
        self.assertEqual(task["status"], "WRONG_OUTPUT")

    def test_missing_phase_is_retained_as_failure(self):
        def remove_phase(w, _):
            w["phase_events"].pop("QueryGen")
            w["phase_ns"].pop("QueryGen")
        _, task, _ = self.run_protocol(worker_transform=remove_phase)
        self.assertIn(task["status"], ("WRONG_OUTPUT", "RUNTIME_FAIL"))
        self.assertFalse(task["validation_passed"])

    def test_unknown_native_status_is_retained_as_runtime_failure(self):
        def corrupt_status(w, _):
            w["status"] = "UNRECOGNIZED_SYNTHETIC_STATUS"
        _, task, _ = self.run_protocol(worker_transform=corrupt_status)
        self.assertEqual(task["status"], "RUNTIME_FAIL")

    def test_missing_fingerprint_cannot_pass_packed_worker(self):
        def remove_fingerprint(w, _):
            w.pop("key_fingerprint")
        _, task, _ = self.run_protocol(method="packed", worker_transform=remove_fingerprint)
        self.assertNotEqual(task["status"], "COMPLETE")

    def test_worker_exit_zero_cannot_replace_global_timeout(self):
        _, task, workers = self.run_protocol(hard_deadline=10500)
        self.assertEqual(task["status"], "TIMEOUT")
        self.assertTrue(all(w["status"] == "TIMEOUT" and not w["output_verified"] for w in workers))


if __name__ == "__main__":
    unittest.main()
