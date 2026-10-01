#!/usr/bin/env python3
"""Finite native functional gate; diagnostic timings are not performance data.

SPDX-License-Identifier: GPL-3.0-or-later
Every output is new and stays under experiments/core_rebuild/runs.
Compilation is a separate, explicitly controlled phase.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from common import CORE, ROOT, EMAX, N, Q, W, config, integer_screen, layout, normalize, sha, write_new
from resources import GroupResources, MeasurementLock
from runner import PublicFixture, TaskRunner, SEALS


def cases():
    """All legal candidate width/count combinations, plus exact bit boundaries."""
    rows = []
    for alpha in (1, 2, 3, 4):
        for rho in (4, 6, 8, 12, 16, 24):
            if alpha * rho > W:
                continue
            for kind in ('zero', 'max', 'equal', 'random'):
                rows.append({'case_id': f'a{alpha}_rho{rho:02}_short_{kind}',
                             'alpha': alpha, 'rho': rho, 'ell': 2 * rho + 1,
                             'kind': kind, 'category': 'segments_and_padding'})
            for suffix, ell in (('before', N * rho - 1), ('exact', N * rho),
                                ('after', N * rho + 1), ('two_blocks', 2 * N * rho)):
                rows.append({'case_id': f'a{alpha}_rho{rho:02}_{suffix}',
                             'alpha': alpha, 'rho': rho, 'ell': ell,
                             'kind': 'random', 'category': 'bit_exact_block_boundary'})
    assert len(rows) == 120
    return rows


def accept(directory, observation, workload, cfg, fingerprints):
    if observation['status'] != 'COMPLETE' or not observation['validated']:
        raise AssertionError('task functional acceptance failed: ' + repr(observation.get('failure_reasons')))
    native = [normalize(json.loads((directory / rel).read_text()))
              for rel in observation['native_outputs']]
    prep, queries = native[0], native[1:]
    expected_queries = 1 if cfg['kind'] == 'P' else workload['alpha']
    blocks = layout(workload['ell_bits'], cfg['rho_0'])['L']
    assert len(queries) == expected_queries
    assert prep['native_import_owner_released_before_done'] and prep['import_calls'] == 1
    assert observation['shared_seals'] & SEALS == SEALS
    assert observation['query_count'] == expected_queries
    assert observation['import_calls'] == 1 and observation['readonly_shared_data']
    assert observation['query_buffer_bytes'] == expected_queries * workload['N'] * 131072
    assert observation['reply_buffer_bytes'] == expected_queries * blocks * 131072
    assert observation['collected_record_bytes'] == workload['alpha'] * ((workload['ell_bits'] + 7) // 8)
    for value in queries:
        assert (value['n'], value['w'], value['q']) == (N, W, Q)
        assert value['key_generation_calls'] == value['key_rng_calls'] == 1
        assert value['rng_calls'] == 1 + 2 * workload['N']
        assert value['query_rng_calls'] == 2 * workload['N']
        assert value['rng_nonce_sequence']
        assert value['L'] == blocks and value['query_ciphertexts'] == workload['N']
        assert value['reply_ciphertexts'] == blocks
        assert value['mapping_read_only'] and value['private_import_calls'] == 0
        assert value['output_verified'] and value['all_coefficients_exact']
        assert value['all_segments_exact'] and value['padding_exact']
        assert value['validation_after_gate'] and value['direct_weight_encryption']
        assert value['audit_error_queries'] == workload['N']
        assert 0 <= value['observed_error_max'] <= EMAX
        # This is an initialization diagnostic, not a security or collision-probability proof.
        fingerprint = value['first_ciphertext_fingerprint']
        assert re.fullmatch(r'[0-9a-f]{64}', fingerprint)
        assert fingerprint not in fingerprints, 'fresh-exec ciphertext fingerprint repeated'
        fingerprints.add(fingerprint)
    return {'query_processes': len(queries), 'blocks': blocks,
            'observed_error_max': max(q['observed_error_max'] for q in queries),
            'native_report_sha256': {rel: sha(directory / rel) for rel in observation['native_outputs']}}


def run_unit(binary, directory):
    command = [str(binary), str(directory / 'readonly_mapping_probe.bin')]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=120, check=False)
    with (directory / 'native_unit.log').open('xb') as stream:
        stream.write(result.stdout)
    lines = result.stdout.decode('utf-8', errors='replace').splitlines()
    report = json.loads(lines[-1]) if lines else {}
    assert result.returncode == 0 and report.get('status') == 'PASS_NATIVE_WRAPPER_UNIT'
    assert report['cryptographic_initializations'] == report['measurements'] == 0
    write_new(directory / 'native_unit.json', {'command': command, 'returncode': result.returncode,
                                             'binary_sha256': sha(binary), 'result': report})
    return report


def reject_domains(binary, directory):
    base = {'N': 8, 'ell_bits': 17, 'rho_0': 8, 'w': 24,
            'fixture_seed': 987654321, 'targets': [7, 0],
            'shared_path': str(directory / 'absent_mapping.bin')}
    examples = [('wrong_width', {'w': 25}), ('zero_records', {'N': 0}),
                ('zero_length', {'ell_bits': 0}), ('zero_rho', {'rho_0': 0}),
                ('overwide_rho', {'rho_0': 25}), ('duplicate_targets', {'targets': [1, 1]}),
                ('out_of_range_target', {'targets': [8, 0]}),
                ('overcapacity', {'rho_0': 12, 'targets': [7, 0, 6]}),
                ('thread_budget', {'threads': 5})]
    results = []
    for name, changes in examples:
        job = dict(base, **changes)
        job_path = directory / (name + '_job.json')
        output = directory / (name + '_native.json')
        write_new(job_path, job)
        command = [str(binary), 'query', str(job_path), str(output)]
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 timeout=30, check=False)
        with (directory / (name + '.log')).open('xb') as stream:
            stream.write(process.stdout)
        report = normalize(json.loads(output.read_text()))
        assert process.returncode == 21 and report['status'] == 'FAILED'
        assert report.get('failure_reason') and 'cannot open' not in report['failure_reason']
        results.append({'case_id': name, 'returncode': process.returncode,
                        'failure_reason': report['failure_reason'], 'report_sha256': sha(output)})
    write_new(directory / 'rejection_report.json', results)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--functional-id', default='functional_001')
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--unit-binary', type=Path, required=True)
    parser.add_argument('--policy', choices=('monitor', 'cgroup'), required=True)
    parser.add_argument('--cpus', required=True, help='comma-separated selected CPU IDs')
    parser.add_argument('--authorize-cgroup-write', action='store_true')
    parser.add_argument('--cgroup-parent', type=Path)
    args = parser.parse_args()
    for value in (args.run_id, args.functional_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
            raise ValueError('run/functional IDs must be simple unused leaf names')
    cpus = [int(value) for value in args.cpus.split(',')]
    if len(cpus) != len(set(cpus)) or not 1 <= len(cpus) <= 4:
        raise ValueError('functional gate uses one to four distinct selected CPUs')
    binary, unit_binary = args.binary.resolve(), args.unit_binary.resolve()
    for path in (binary, unit_binary):
        if not path.is_file() or not path.is_relative_to(CORE.resolve()):
            raise ValueError('use new isolated core build binaries')
    directory = CORE / 'runs' / args.run_id / 'functional' / args.functional_id
    directory.mkdir(parents=True, exist_ok=False)
    planned = cases()
    write_new(directory / 'cases.json', planned)
    started = time.time_ns()
    report = {'status': 'FUNCTIONAL_INCOMPLETE', 'timing_label': 'FUNCTIONAL_ONLY_NOT_FOR_PERFORMANCE',
              'native_binary_sha256': sha(binary), 'unit_binary_sha256': sha(unit_binary),
              'source_hashes': {str(p.relative_to(ROOT)): sha(p) for p in
                                (Path(__file__), CORE / 'src/core_native.cpp', CORE / 'src/core_native.hpp',
                                 CORE / 'tests/test_native_unit.cpp')},
              'planned_layout_cases': len(planned), 'completed': [], 'failures': [],
              'performance_observations': 0,
              'scope_note': 'Diagnostic clocks retained in raw reports; gate timings do not enter performance analysis.'}
    fingerprints = set()
    try:
        with MeasurementLock(ROOT, args.run_id + '_functional'), GroupResources(
                cpus, run_id=args.run_id + '_functional', memory_policy=args.policy,
                authorize_cgroup_write=args.authorize_cgroup_write,
                cgroup_parent=args.cgroup_parent) as resources:
            report['wrapper_unit'] = run_unit(unit_binary, directory)
            rejection_dir = directory / 'invalid_domains'
            rejection_dir.mkdir()
            report['rejections'] = reject_domains(binary, rejection_dir)
            runner = TaskRunner(binary, resources, task_timeout=120)
            for index, row in enumerate(planned):
                workload = {'N': 8, 'alpha': row['alpha'], 'ell_bits': row['ell']}
                cfg = config('P', row['rho'], 1, 1 if index % 2 else len(cpus))
                scope = 'included' if index % 2 else 'excluded'
                selected = [7, 0, 6, 1][:row['alpha']]
                task_directory = directory / row['case_id']
                with PublicFixture(8, row['ell'], 202610019000 + index, row['kind']) as public:
                    observation = runner.run(task_directory, workload, cfg, scope, public, selected,
                                             audit_errors=True,
                                             labels={'phase': 'functional', 'case_id': row['case_id'],
                                                     'timing_label': report['timing_label']})
                screen = integer_screen(8, row['ell'], row['alpha'], row['rho'])
                assert screen['strict_no_wrap']
                accepted = accept(task_directory, observation, workload, cfg, fingerprints)
                report['completed'].append(dict(row, scope=scope, integer_screen=screen, **accepted))
            # Identical public inputs still start two fresh exec/query states.
            with PublicFixture(8, 97, 202610019999, 'random') as public:
                workload = {'N': 8, 'alpha': 4, 'ell_bits': 97}
                cfg = config('P', 6, 1, 1)
                for repeat in range(2):
                    task_directory = directory / f'fresh_repeat_{repeat}'
                    observation = runner.run(task_directory, workload, cfg, 'excluded', public, [7, 0, 6, 1],
                                             audit_errors=True, labels={'phase': 'functional', 'timing_label': report['timing_label']})
                    report['completed'].append({'case_id': task_directory.name,
                                                **accept(task_directory, observation, workload, cfg, fingerprints)})
            # Serial and legal concurrent repeated tasks share exactly one import owner.
            policies = {(1, len(cpus)), (min(4, len(cpus)), len(cpus) // min(4, len(cpus)))}
            for rho in (6, 24):
                ell = N * rho + 1
                with PublicFixture(8, ell, 202610018000 + rho, 'max') as public:
                    workload = {'N': 8, 'alpha': 4, 'ell_bits': ell}
                    for concurrency, threads in sorted(policies):
                        cfg = config('R', rho, concurrency, threads)
                        for scope in ('included', 'excluded'):
                            task_directory = directory / f'{cfg["config_id"]}_{scope}'
                            observation = runner.run(task_directory, workload, cfg, scope, public, [7, 0, 6, 1],
                                                     audit_errors=True, labels={'phase': 'functional', 'timing_label': report['timing_label']})
                            report['completed'].append({'case_id': task_directory.name,
                                                        **accept(task_directory, observation, workload, cfg, fingerprints)})
            report['status'] = 'PASS_FINITE_NATIVE_FUNCTIONAL_GATE'
    except BaseException as error:
        report['failures'].append({'type': type(error).__name__, 'message': str(error)})
    finally:
        report['finished_time_ns'] = time.time_ns()
        report['elapsed_ns'] = report['finished_time_ns'] - started
        report['fresh_ciphertext_fingerprints_checked'] = len(fingerprints)
        report['complete_native_tasks'] = len(report['completed'])
        write_new(directory / 'functional_report.json', report)
    print(json.dumps({'status': report['status'], 'report': str(directory / 'functional_report.json'),
                      'complete_native_tasks': report['complete_native_tasks'], 'failures': report['failures']}))
    if report['status'] != 'PASS_FINITE_NATIVE_FUNCTIONAL_GATE':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
