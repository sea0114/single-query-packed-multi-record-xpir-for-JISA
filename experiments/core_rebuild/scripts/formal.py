#!/usr/bin/env python3
"""Execute only the literal frozen schedule; preserve failed/unstarted rows.
SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse
from collections import Counter
import datetime
import hashlib
import itertools
import json
import os
from pathlib import Path
import time
from common import CORE, ROOT, now, sha, write_new
from preflight import inventory
from resources import GroupResources, MeasurementLock
from runner import PublicFixture, TaskRunner


KEY_FIELDS = ('condition_id', 'session_id', 'block_id', 'phase', 'config_id')


class FormalBudgetExceeded(RuntimeError):
    pass


def physical_key(row):
    return tuple(row[k] for k in KEY_FIELDS)


def observation_id(row):
    return (f's{row["session_id"]:02}_b{row["block_id"]}_'
            f'{row["condition_id"]}_{row["config_id"]}')


def validate_protocol(freeze, conditions):
    """Reject altered schedules before any native measurement starts."""
    if len(conditions) != len(freeze['conditions']):
        raise ValueError('Duplicate frozen condition')
    sessions = list(range(1, freeze['sessions'] + 1))
    if freeze['sessions'] != 10 or freeze['warmup_blocks'] != 1 or freeze['measured_blocks_per_session'] != 6:
        raise ValueError('Frozen repetition protocol changed')
    blocks = {}
    condition_blocks = {}
    session_order = []
    literal_expected = []
    for condition in conditions.values():
        roles = condition['roles']
        if set(roles) != {'P', 'R_matched', 'R_independent'}:
            raise ValueError('Frozen method roles changed')
        if roles['P'] in {roles['R_matched'], roles['R_independent']}:
            raise ValueError('Packed and repeated configurations must differ')
        if set(condition['configurations']) != set(roles.values()):
            raise ValueError('Frozen configurations do not match physical roles')
        if condition['baseline_alias'] != (roles['R_matched'] == roles['R_independent']):
            raise ValueError('Frozen baseline alias mismatch')
    for block in freeze['schedule']:
        if not session_order or session_order[-1] != block['session_id']:
            session_order.append(block['session_id'])
        condition = conditions[block['condition_id']]
        if block['session_id'] not in sessions or block['block_id'] not in range(7):
            raise ValueError('Frozen session/block outside protocol')
        phase = 'warmup' if block['block_id'] == 0 else 'measured'
        if block['phase'] != phase:
            raise ValueError('Frozen warmup/measured label mismatch')
        order = block['order']
        if len(order) != len(set(order)) or set(order) != set(condition['configurations']):
            raise ValueError('Frozen block omits or duplicates a physical method')
        targets = block['targets']
        workload = condition['workload']
        if (len(targets) != workload['alpha'] or len(set(targets)) != len(targets)
                or any(not isinstance(i, int) or isinstance(i, bool) or i < 0 or i >= workload['N'] for i in targets)):
            raise ValueError('Frozen ordered targets are inadmissible')
        block_key = (block['condition_id'], block['session_id'], block['block_id'])
        if block_key in blocks:
            raise ValueError('Duplicate frozen block')
        blocks[block_key] = block
        condition_blocks.setdefault((block['condition_id'], block['session_id']), []).append(block['block_id'])
        for cid in order:
            literal_expected.append(physical_key(dict(block, config_id=cid)))
    for cid, condition in conditions.items():
        ids = sorted(condition['configurations'])
        expected_orders = Counter(itertools.permutations(ids))
        if len(ids) == 2:
            expected_orders = Counter({order: 3 for order in expected_orders})
        if len(ids) not in (2, 3):
            raise ValueError('Frozen physical method count changed')
        for session in sessions:
            if condition_blocks.get((cid, session)) != list(range(7)):
                raise ValueError('Frozen warmup must precede its six measured blocks')
            if any((cid, session, block) not in blocks for block in range(7)):
                raise ValueError('Frozen condition/session is incomplete')
            actual_orders = Counter(tuple(blocks[(cid, session, block)]['order']) for block in range(1, 7))
            if actual_orders != expected_orders:
                raise ValueError('Frozen measured method orders are not balanced')
    if session_order != sessions:
        raise ValueError('Frozen sessions must be contiguous batches in session order')
    expected = [physical_key(row) for row in freeze['expected_observations']]
    if expected != literal_expected or len(expected) != len(set(expected)):
        raise ValueError('Frozen expected observations differ from literal schedule')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--freeze', type=Path, required=True)
    args = parser.parse_args()
    freeze_bytes = args.freeze.read_bytes()
    freeze = json.loads(freeze_bytes)
    run = (CORE / 'runs' / freeze['run_id']).resolve()
    if not run.is_relative_to((CORE / 'runs').resolve()) or run == (CORE / 'runs').resolve():
        raise ValueError('Formal output must remain in a new core_rebuild run')
    output = run / 'raw/formal_001'
    output.mkdir(parents=True, exist_ok=False)
    freeze_hash = hashlib.sha256(freeze_bytes).hexdigest()
    expected_rows = freeze['expected_observations']
    conditions = {c['condition_id']: c for c in freeze['conditions']}
    start = now()
    deadline = start + freeze['budgets_seconds']['formal'] * 1_000_000_000
    rows, not_started, phase_errors, preservation_errors = [], [], [], []
    stopped = None
    last_session = last_session_start = None
    closed_sessions, session_records = set(), []
    pending_attempt = None
    lock = MeasurementLock(ROOT, freeze['run_id'] + '-formal')
    lock_acquired = False

    def check_budget():
        if now() >= deadline:
            raise FormalBudgetExceeded('Frozen formal budget reached')

    def labels_for(block, cid, method_index):
        condition = conditions[block['condition_id']]
        labels = {k: block[k] for k in ('condition_id', 'session_id', 'block_id', 'phase')}
        labels.update(config_id=cid, observation_id=observation_id(dict(block, config_id=cid)),
                      run_id=freeze['run_id'], freeze_sha256=freeze_hash,
                      method_order_index=method_index,
                      method_roles=[role for role, config_id in condition['roles'].items() if config_id == cid])
        return labels

    def append_row(stream, row):
        # Retain the row in memory before an IO exception can interrupt its ledger write.
        rows.append(row)
        stream.write(json.dumps(row, allow_nan=False) + '\n')
        stream.flush()

    def close_session(session):
        if session is None or session in closed_sessions:
            return
        closed_sessions.add(session)
        expected = {physical_key(row) for row in expected_rows if row['session_id'] == session}
        observed = [row for row in rows if row['session_id'] == session]
        accepted = {physical_key(row) for row in observed
                    if row['status'] == 'COMPLETE' and row.get('validated') is True}
        end = now()
        record = {'session_id': session, 'start_ns': last_session_start, 'end_ns': end,
                  'elapsed_ns': end - last_session_start,
                  'complete': accepted == expected,
                  'expected_tasks': len(expected), 'executed_tasks': len(observed),
                  'complete_tasks': len(accepted), 'not_started_tasks': len(expected - {physical_key(row) for row in observed}),
                  'stopped_reason': stopped}
        session_records.append(record)
        write_new(output / 'sessions' / f'{session:02}_end.json', record)

    with (output / 'observations.jsonl').open('x', encoding='utf-8') as stream:
        try:
            validate_protocol(freeze, conditions)
            binary = ROOT / freeze['binary']
            if sha(binary) != freeze['binary_sha256']:
                raise RuntimeError('Frozen binary changed')
            for name, digest in freeze['source_hashes'].items():
                if sha(ROOT / name) != digest:
                    raise RuntimeError('Frozen source changed: ' + name)
            manifest_bytes = (ROOT / freeze['build_manifest']).read_bytes()
            if hashlib.sha256(manifest_bytes).hexdigest() != freeze['build_manifest_sha256']:
                raise RuntimeError('Frozen build manifest changed')
            build = json.loads(manifest_bytes)
            for name, digest in build['upstream_files'].items():
                if sha(ROOT / name) != digest:
                    raise RuntimeError('Pinned upstream changed: ' + name)
            for name, digest in build['libraries'].items():
                if sha(Path(name)) != digest:
                    raise RuntimeError('Linked dependency changed: ' + name)
            check_budget()
            with lock:
                lock_acquired = True
                write_new(output / 'lock_provenance.json', lock.record)
                with GroupResources(freeze['cpu_pool'], run_id=freeze['run_id'] + '-formal',
                                    memory_limit_bytes=freeze['memory_threshold_bytes'],
                                    memory_policy=freeze['resource_policy'],
                                    authorize_cgroup_write=freeze['resource_policy'] == 'cgroup') as resources:
                    runner = TaskRunner(binary, resources, deadline=deadline,
                                        monitor_interval=freeze['monitor_interval_seconds'])
                    for block in freeze['schedule']:
                        check_budget()
                        session = block['session_id']
                        if session != last_session:
                            close_session(last_session)
                            if last_session is not None:
                                time.sleep(min(freeze['session_interval_seconds'], max(0, (deadline - now()) / 1e9)))
                            check_budget()
                            last_session, last_session_start = session, now()
                            environment = inventory()
                            write_new(output / 'sessions' / f'{session:02}_start.json',
                                      {'session_id': session, 'start_ns': last_session_start,
                                       'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                       'environment': environment,
                                       'session_note': 'Same-host fresh batch, not an independent host/day'})
                        check_budget()
                        condition = conditions[block['condition_id']]
                        workload = condition['workload']
                        with PublicFixture(workload['N'], workload['ell_bits'], block['fixture_seed']) as fixture:
                            for method_index, cid in enumerate(block['order']):
                                check_budget()
                                labels = labels_for(block, cid, method_index)
                                pending_attempt = dict(labels, status='FAILED', validated=False,
                                                       reason='Formal coordinator exception during task dispatch')
                                row = runner.run(output / 'tasks' / labels['observation_id'], workload,
                                                 condition['configurations'][cid], condition['scope'],
                                                 fixture, block['targets'], labels=labels)
                                pending_attempt = None
                                append_row(stream, row)
                                print(json.dumps({'completed_tasks': len(rows), 'expected_tasks': len(expected_rows),
                                                  'session_id': session, 'condition_id': block['condition_id'],
                                                  'phase': block['phase'], 'block_id': block['block_id'],
                                                  'config_id': cid, 'status': row['status'],
                                                  'phase_elapsed_seconds': (now() - start) / 1e9}), flush=True)
                                if row['status'] != 'COMPLETE' or row.get('validated') is not True:
                                    stopped = 'FORMAL_BUDGET' if now() >= deadline else 'TASK_FAILURE'
                                    break
                        if stopped:
                            break
        except BaseException as error:
            stopped = ('FORMAL_BUDGET' if isinstance(error, FormalBudgetExceeded)
                       else 'INTERRUPTED' if isinstance(error, KeyboardInterrupt) else 'PHASE_EXCEPTION')
            detail = {'type': type(error).__name__, 'message': str(error)}
            phase_errors.append(detail)
            if pending_attempt is not None:
                pending_attempt['failure_reasons'] = [detail['type'] + ': ' + detail['message']]
                try:
                    append_row(stream, pending_attempt)
                except BaseException as preserve_error:
                    preservation_errors.append({'stage': 'attempted_task_row', 'type': type(preserve_error).__name__,
                                                'message': str(preserve_error)})
        finally:
            try:
                close_session(last_session)
            except BaseException as error:
                stopped = stopped or 'PRESERVATION_FAILURE'
                preservation_errors.append({'stage': 'session_end', 'type': type(error).__name__, 'message': str(error)})
            observed_keys = {physical_key(row) for row in rows}
            for expected in expected_rows:
                if physical_key(expected) in observed_keys:
                    continue
                condition = conditions.get(expected['condition_id'], {})
                cid = expected['config_id']
                row = dict(expected, observation_id=observation_id(expected), run_id=freeze['run_id'],
                           status='NOT_STARTED', validated=False, reason=stopped or 'Unexpected schedule omission',
                           freeze_sha256=freeze_hash,
                           method_roles=[role for role, config_id in condition.get('roles', {}).items() if config_id == cid])
                not_started.append(row)
                try:
                    stream.write(json.dumps(row, allow_nan=False) + '\n')
                except BaseException as error:
                    stopped = stopped or 'PRESERVATION_FAILURE'
                    preservation_errors.append({'stage': 'not_started_row', 'observation_id': row['observation_id'],
                                                'type': type(error).__name__, 'message': str(error)})
            try:
                stream.flush()
                os.fsync(stream.fileno())
            except BaseException as error:
                stopped = stopped or 'PRESERVATION_FAILURE'
                preservation_errors.append({'stage': 'observations_flush', 'type': type(error).__name__, 'message': str(error)})
    complete = (not stopped and not not_started and not preservation_errors
                and len(rows) == len(expected_rows)
                and all(row['status'] == 'COMPLETE' and row.get('validated') is True for row in rows))
    report = {'status': 'COMPLETE' if complete else 'INCOMPLETE', 'run_id': freeze['run_id'],
              'freeze_sha256': freeze_hash, 'tier': freeze['tier'], 'conditions': len(freeze['conditions']),
              'sessions': freeze['sessions'], 'session_completion': session_records,
              'expected_physical_tasks': len(expected_rows), 'executed_tasks': len(rows),
              'complete_tasks': sum(row['status'] == 'COMPLETE' and row.get('validated') is True for row in rows),
              'not_started_tasks': len(not_started),
              'failed_tasks': sum(row['status'] != 'COMPLETE' or row.get('validated') is not True for row in rows),
              'stopped_reason': stopped, 'phase_errors': phase_errors, 'preservation_errors': preservation_errors,
              'elapsed_seconds': (now() - start) / 1e9, 'budget_seconds': freeze['budgets_seconds']['formal'],
              'observations_sha256': sha(output / 'observations.jsonl'),
              'measurement_lock_acquired': lock_acquired,
              'measurement_lock_released': lock.record is None if lock_acquired else None}
    try:
        write_new(output / 'formal_report.json', report)
    except BaseException as error:
        report['status'] = 'INCOMPLETE'
        report['preservation_errors'].append({'stage': 'formal_report', 'type': type(error).__name__, 'message': str(error)})
    print(json.dumps(report, allow_nan=False), flush=True)
    return 0 if report['status'] == 'COMPLETE' else 2


if __name__ == '__main__':
    raise SystemExit(main())
