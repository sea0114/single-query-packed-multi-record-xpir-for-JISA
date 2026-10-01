#!/usr/bin/env python3
"""Fresh-exec, sealed shared preprocessing and complete-task measurement.

SPDX-License-Identifier: GPL-3.0-or-later
"""
from __future__ import annotations
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import selectors
import subprocess
import threading
import time

from common import CORE, Q, W, fixture_bytes, layout, normalize, now, write_new
from resources import MemoryLimitExceeded, scan_competing_processes, shared_fd_identity

SEALS = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL


class DeadlineExceeded(RuntimeError):
    pass


def self_cpu():
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return int((usage.ru_utime + usage.ru_stime) * 1e9)


class PublicFixture:
    """Public records shared between every method in a paired block."""
    def __init__(self, records, ell, seed, kind='random'):
        self.N, self.ell, self.seed, self.kind = records, ell, seed, kind
        self.data = fixture_bytes(records, ell, seed, kind)
        self.sha256 = hashlib.sha256(self.data).hexdigest()
        self.fd = os.memfd_create('core-public-fixture', os.MFD_ALLOW_SEALING)
        try:
            offset = 0
            while offset < len(self.data):
                offset += os.write(self.fd, self.data[offset:])
            fcntl.fcntl(self.fd, fcntl.F_ADD_SEALS, SEALS)
        except BaseException:
            os.close(self.fd)
            raise

    def expected(self, targets):
        width = (self.ell + 7) // 8
        return b''.join(self.data[i * width:(i + 1) * width] for i in targets)

    def close(self):
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()


class NativeProcess:
    def __init__(self, binary, directory, name, role, job, fds, cpus):
        self.name, self.role = name, role
        self.directory = directory
        self.ready, ready_write = os.pipe()
        go_read, self.go = os.pipe()
        self.data = None
        data_write = -1
        if role == 'query':
            self.data, data_write = os.pipe()
        job = dict(job, ready_fd=ready_write, go_fd=go_read, data_fd=data_write)
        self.job_path = directory / (name + '_job.json')
        self.output_path = directory / (name + '_native.json')
        write_new(self.job_path, job)
        command = ['taskset', '-c', ','.join(map(str, cpus)), str(binary), role,
                   str(self.job_path), str(self.output_path)]
        self.command = command
        self.log = bytearray()
        inherited = tuple(fds) + (ready_write, go_read) + ((data_write,) if data_write >= 0 else ())
        try:
            self.process = subprocess.Popen(command, pass_fds=inherited, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, start_new_session=True)
        finally:
            os.close(ready_write)
            os.close(go_read)
            if data_write >= 0:
                os.close(data_write)
        self.reader = threading.Thread(target=self._drain_log, daemon=True)
        self.reader.start()
        self.ready_state = bytearray()
        self.records = bytearray()
        self.started = False

    def _drain_log(self):
        while True:
            chunk = self.process.stdout.read(65536)
            if not chunk:
                break
            self.log.extend(chunk)

    def start(self):
        os.write(self.go, b'G')
        self.started = True

    def finish(self):
        os.write(self.go, b'V')

    def close(self):
        for fd in (self.ready, self.go, self.data):
            if fd is not None:
                os.close(fd)
        self.reader.join(timeout=5)
        self.process.stdout.close()
        with (self.directory / (self.name + '.log')).open('xb') as stream:
            stream.write(self.log)


class TaskRunner:
    def __init__(self, binary, resources, *, deadline=None, monitor_interval=1.0,
                 task_timeout=300.0):
        self.binary = Path(binary).resolve()
        self.resources = resources
        self.deadline = deadline  # CLOCK_MONOTONIC_RAW nanoseconds, phase budget
        self.monitor_interval = monitor_interval
        self.task_timeout = task_timeout
        self.tasks = 0

    def run(self, directory, workload, cfg, scope, fixture, selected_targets,
            *, audit_errors=False, labels=None):
        directory = Path(directory).resolve()
        if not directory.is_relative_to(CORE.resolve()):
            raise ValueError('task output must remain in core_rebuild')
        directory.mkdir(parents=True, exist_ok=False)
        wall_start = now()
        deadline = wall_start + int(self.task_timeout * 1e9)
        if self.deadline is not None:
            deadline = min(deadline, self.deadline)
        if scope not in ('included', 'excluded'):
            raise ValueError('unknown preprocessing scope')
        if len(selected_targets) != workload['alpha'] or len(set(selected_targets)) != len(selected_targets):
            raise ValueError('ordered target count')
        if cfg['concurrency'] * cfg['threads'] > len(self.resources.cpu_pool):
            raise ValueError('execution policy exceeds total CPU allowance')
        if cfg['kind'] == 'P' and cfg['concurrency'] != 1:
            raise ValueError('packed task must have one query')
        db_fd = os.memfd_create('core-preprocessed-database', os.MFD_ALLOW_SEALING)
        identity = shared_fd_identity(db_fd)
        children, samples, failures = [], [], []
        last_monitor = 0
        last_competition = 0
        result = dict(labels or {})
        result.update(config_id=cfg['config_id'], configuration=cfg, scope=scope,
                      workload=workload, targets=selected_targets,
                      fixture_seed=fixture.seed, fixture_kind=fixture.kind,
                      fixture_sha256=fixture.sha256, status='FAILED', validated=False)
        selector = selectors.DefaultSelector()
        cpus = sorted(self.resources.cpu_pool)
        common = {'N': workload['N'], 'ell_bits': workload['ell_bits'],
                  'rho_0': cfg['rho_0'], 'w': W, 'fixture_seed': fixture.seed,
                  'fixture_sha256': fixture.sha256,
                  'shared_path': f'/proc/self/fd/{db_fd}',
                  'raw_path': f'/proc/self/fd/{fixture.fd}', 'db_fd': db_fd}

        def check():
            nonlocal last_monitor, last_competition
            tick = now()
            if tick >= deadline:
                raise DeadlineExceeded('task or phase deadline reached')
            if tick - last_monitor >= int(self.monitor_interval * 1e9):
                # Public raw memfd is also unique physical storage. The Python
                # public bytes remain resident and are included in private PSS.
                shared = os.fstat(db_fd).st_size + os.fstat(fixture.fd).st_size
                samples.append(self.resources.monitor([c.process.pid for c in children],
                                                       shared_bytes=shared,
                                                       shared_identity=identity))
                last_monitor = tick
            if tick - last_competition >= 2_000_000_000:
                allowed = {os.getpid(), *(c.process.pid for c in children)}
                competing = scan_competing_processes(allowed_pids=allowed)
                if competing:
                    raise RuntimeError('competing heavy work: ' + repr(competing))
                last_competition = tick
            for child in children:
                code = child.process.poll()
                if code is not None and code != 0:
                    raise RuntimeError(f'{child.name} exited {code} before acceptance')

        def pump(predicate):
            while not predicate():
                check()
                for key, unused in selector.select(0.02):
                    child, stream = key.data
                    value = os.read(key.fd, 65536)
                    if not value:
                        selector.unregister(key.fd)
                        continue
                    if stream == 'ready':
                        child.ready_state.extend(value)
                        if child.ready_state not in (b'R', b'RD'):
                            raise RuntimeError('invalid native barrier sequence')
                    else:
                        child.records.extend(value)

        def spawn(name, role, job, affinity):
            child = NativeProcess(self.binary, directory, name, role, job,
                                  (db_fd, fixture.fd), affinity)
            children.append(child)
            selector.register(child.ready, selectors.EVENT_READ, (child, 'ready'))
            if child.data is not None:
                selector.register(child.data, selectors.EVENT_READ, (child, 'data'))
            return child

        timer_start = timer_end = cpu_before = cpu_after = None
        group_before = group_after = None
        try:
            check()
            owner = spawn('prepare', 'prepare', dict(common, threads=len(cpus)), cpus)
            target_groups = [selected_targets] if cfg['kind'] == 'P' else [[i] for i in selected_targets]
            queries = []
            for index, target_group in enumerate(target_groups):
                slot = index % cfg['concurrency']
                affinity = cpus[slot * cfg['threads']:(slot + 1) * cfg['threads']]
                queries.append(spawn(f'query_{index:02}', 'query',
                                     dict(common, threads=cfg['threads'], targets=target_group,
                                          audit_errors=audit_errors, audit=True), affinity))
            pump(lambda: all(c.ready_state == b'R' for c in children))
            if scope == 'included':
                group_before = self.resources.cpu_snapshot()
                cpu_before = self_cpu()
                timer_start = now()
            owner.start()
            pump(lambda: owner.ready_state == b'RD')
            fcntl.fcntl(db_fd, fcntl.F_ADD_SEALS, SEALS)
            result['shared_seals'] = fcntl.fcntl(db_fd, fcntl.F_GET_SEALS)
            result['shared_bytes'] = os.fstat(db_fd).st_size
            if scope == 'excluded':
                group_before = self.resources.cpu_snapshot()
                cpu_before = self_cpu()
                timer_start = now()
            active, next_query = [], 0
            occupied = {}
            width = (workload['ell_bits'] + 7) // 8
            while next_query < len(queries) or active:
                while next_query < len(queries) and len(active) < cfg['concurrency']:
                    child = queries[next_query]
                    slot = next(s for s in range(cfg['concurrency']) if s not in occupied.values())
                    os.sched_setaffinity(child.process.pid, cpus[slot * cfg['threads']:(slot + 1) * cfg['threads']])
                    child.start()
                    active.append(child)
                    occupied[child] = slot
                    next_query += 1
                pump(lambda: any(c.ready_state == b'RD' and len(c.records) == width * len(target_groups[queries.index(c)]) for c in active))
                done = [c for c in active if c.ready_state == b'RD' and len(c.records) == width * len(target_groups[queries.index(c)])]
                for child in done:
                    del occupied[child]
                    active.remove(child)
            timer_end = now()
            cpu_after = self_cpu()
            group_after = self.resources.cpu_snapshot()
            # The last output byte and DONE are received before validation or
            # per-process metadata/log writing is released.
            for child in children:
                child.finish()
            for child in children:
                remaining = max(0.001, (deadline - now()) / 1e9)
                child.process.wait(timeout=remaining)
            native = [normalize(json.loads(c.output_path.read_text())) for c in children]
            prep, outputs = native[0], native[1:]
            recovered = b''.join(bytes(c.records) for c in queries)
            if recovered != fixture.expected(selected_targets):
                raise RuntimeError('coordinator full-record comparison failed')
            for value in native:
                if value['status'] != 'COMPLETE' or value['n'] != 4096 or value['w'] != 24 or int(value['q']) != Q:
                    raise RuntimeError('native parameter or output acceptance failed')
            if prep['import_calls'] != 1 or not prep['native_import_owner_released_before_done']:
                raise RuntimeError('preprocessing ownership acceptance failed')
            for value in outputs:
                if not (value['output_verified'] and value['all_coefficients_exact'] and value['padding_exact']
                        and value['mapping_read_only'] and value['private_import_calls'] == 0
                        and value['key_generation_calls'] == 1 and value['key_rng_calls'] == 1
                        and value['query_rng_calls'] == 2 * workload['N']):
                    raise RuntimeError('query acceptance failed')
            if group_before['source'] == 'cgroup_v2_cpu.stat':
                cpu_total = sum(group_after[k] - group_before[k] for k in ('user_ns', 'system_ns'))
                cpu_source = 'cgroup_v2_cpu.stat_same_task_span'
            else:
                timed_children = outputs + ([prep] if scope == 'included' else [])
                cpu_total = cpu_after - cpu_before + sum(v['cpu_user_ns'] + v['cpu_system_ns'] for v in timed_children)
                cpu_source = 'coordinator_self_rusage_plus_native_G_to_D_rusage_including_exited_children'
            result.update(status='COMPLETE', validated=True,
                          task_latency_ns=timer_end - timer_start,
                          cpu_time_ns=cpu_total, cpu_source=cpu_source,
                          preprocessing_ns=prep['preprocess_total_ns'],
                          query_buffer_bytes=sum(v['query_buffer_bytes'] for v in outputs),
                          reply_buffer_bytes=sum(v['reply_buffer_bytes'] for v in outputs),
                          collected_record_bytes=len(recovered),
                          query_count=len(outputs), key_generation_calls=len(outputs),
                          import_calls=1, readonly_shared_data=True,
                          fingerprints=[v['first_ciphertext_fingerprint'] for v in outputs],
                          native_outputs=[str(c.output_path.relative_to(directory)) for c in children],
                          task_start_ns=timer_start, task_end_ns=timer_end,
                          group_cpu_before=group_before, group_cpu_after=group_after)
        except BaseException as error:
            if isinstance(error, KeyboardInterrupt):
                failures.append('interrupted')
            failures.append(type(error).__name__ + ': ' + str(error))
            result['status'] = 'OOM' if isinstance(error, MemoryLimitExceeded) else 'TIMEOUT' if isinstance(error, (DeadlineExceeded, subprocess.TimeoutExpired)) else 'FAILED'
            if isinstance(error, MemoryLimitExceeded):
                samples.append(error.record)
            for child in children:
                if child.process.poll() is None:
                    # Only fresh processes created by this task are terminated.
                    child.process.kill()
            for child in children:
                child.process.wait()
            result['failure_reasons'] = failures
            if timer_start is not None:
                result['task_start_ns'] = timer_start
                result['failed_elapsed_ns'] = now() - timer_start
        finally:
            selector.close()
            for child in children:
                child.close()
            os.close(db_fd)
            result['wall_elapsed_ns'] = now() - wall_start
            result['resource_policy'] = self.resources.memory_policy
            result['resource_samples'] = len(samples)
            result['commands'] = [c.command for c in children]
            write_new(directory / 'resource_samples.json', samples)
            write_new(directory / 'observation.json', result)
            self.tasks += 1
        return result
