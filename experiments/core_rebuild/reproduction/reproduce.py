#!/usr/bin/env python3
"""Copy an exact portable closure and run frozen analysis or redraw in a new root.

SPDX-License-Identifier: GPL-3.0-or-later
No native executable, historical dataset, manuscript or whole run is copied.
Existing inputs and outputs are never overwritten or removed. Failed attempts
retain their new output tree. Run this only after measurement has fully ended.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys


CORE = Path(__file__).resolve().parents[1]
ROOT = CORE.parents[1]
SCRIPT_NAMES = ('summarize.py', 'analyze.py', 'common.py', 'plots.py')
RESULT_NAMES = {'summary.json', 'fullprecision.csv', 'session_effects.csv',
                'configurations_and_buffers.csv', 'claim_map.json', 'failure_ledger.json'}
FIGURE_NAMES = {'retrieval_performance.pdf', 'capacity_tradeoff.pdf',
                'figure_data.json', 'caption_data.json'}
KEY_FIELDS = ('condition_id', 'session_id', 'block_id', 'phase', 'config_id')
DIGEST = re.compile(r'[0-9a-f]{64}')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest_text(value, name):
    require(isinstance(value, str) and DIGEST.fullmatch(value.lower()),
            name + ' must be an explicit 64-character SHA256')
    return value.lower()


def source_file(relative):
    require(isinstance(relative, str) and '\\' not in relative and ':' not in relative,
            'Closure paths must use portable relative components')
    relative = PurePosixPath(relative)
    require(not relative.is_absolute() and all(p not in ('', '.', '..') for p in relative.parts),
            'Unsafe closure path')
    path = ROOT.joinpath(*relative.parts)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not path.is_symlink(),
            'Closure source is not a regular file: ' + str(relative))
    require(not (getattr(info, 'st_file_attributes', 0)
                 & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)),
            'Closure source is a reparse point: ' + str(relative))
    require(path.resolve().is_relative_to(ROOT.resolve()), 'Closure source escapes checkout')
    return path


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def checked(relative, expected):
    expected = digest_text(expected, relative)
    require(sha(source_file(relative)) == expected, 'Source integrity mismatch: ' + relative)
    return expected


def read_json(relative):
    return json.loads(source_file(relative).read_text(encoding='utf-8'))


def write_new(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def freeze_source_pin(freeze, relative):
    pins = freeze['source_hashes']
    value = pins.get(relative, pins.get(relative.replace('/', '\\')))
    return digest_text(value, 'Frozen source pin for ' + relative)


def verify_formal(run_id, expected_freeze, expected_raw=None, expected_report=None):
    """Verify bytes and the complete physical ledger before any output is created.

    Frozen summarize.py subsequently performs the full scientific validation.
    This wrapper checks provenance, completeness and literal row identities; it
    does not infer effects, select samples or recompute performance statistics.
    """
    prefix = 'experiments/core_rebuild/runs/' + run_id
    paths = {'freeze': prefix + '/provenance/freeze.json',
             'observations': prefix + '/raw/formal_001/observations.jsonl',
             'formal_report': prefix + '/raw/formal_001/formal_report.json'}
    hashes = {'freeze': checked(paths['freeze'], expected_freeze)}
    freeze = read_json(paths['freeze'])
    require(freeze.get('schema') == 'CORE_FREEZE_V1'
            and freeze.get('status') == 'FROZEN_NOT_FORMALLY_MEASURED'
            and freeze.get('run_id') == run_id, 'Freeze identity/schema mismatch')
    require(freeze.get('sessions') == 10 and freeze.get('warmup_blocks') == 1
            and freeze.get('measured_blocks_per_session') == 6,
            'Frozen session protocol differs from the declared design')
    hashes['formal_report'] = sha(source_file(paths['formal_report']))
    if expected_report is not None:
        require(hashes['formal_report'] == digest_text(expected_report, 'Formal report digest'),
                'Formal report integrity mismatch')
    report = read_json(paths['formal_report'])
    require(report.get('status') == 'COMPLETE' and report.get('run_id') == run_id
            and report.get('freeze_sha256') == hashes['freeze'],
            'Formal phase is incomplete or refers to a different freeze')
    hashes['observations'] = checked(paths['observations'], report['observations_sha256'])
    if expected_raw is not None:
        require(hashes['observations'] == digest_text(expected_raw, 'Observation digest'),
                'Formal observation integrity mismatch')
    expected = freeze['expected_observations']
    count = len(expected)
    require(report.get('expected_physical_tasks') == report.get('executed_tasks')
            == report.get('complete_tasks') == count,
            'Formal physical-task counts are incomplete')
    require(report.get('conditions') == len(freeze['conditions'])
            and report.get('sessions') == freeze['sessions']
            and report.get('tier') == freeze['tier'], 'Formal matrix metadata mismatch')
    require(report.get('failed_tasks') == report.get('not_started_tasks') == 0
            and not report.get('stopped_reason') and not report.get('phase_errors')
            and not report.get('preservation_errors'), 'Formal failure/abort ledger is not empty')
    require(report.get('measurement_lock_acquired') is True
            and report.get('measurement_lock_released') is True,
            'Formal measurement lock lifecycle is incomplete')
    sessions = report['session_completion']
    require([s['session_id'] for s in sessions] == list(range(1, 11))
            and all(s.get('complete') is True for s in sessions),
            'Ten complete formal sessions are required')
    actual_count, identities = 0, set()
    with source_file(paths['observations']).open(encoding='utf-8') as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            require(actual_count < count, 'Observation ledger has extra physical rows')
            require(tuple(row[k] for k in KEY_FIELDS)
                    == tuple(expected[actual_count][k] for k in KEY_FIELDS),
                    'Observation order/identity differs from literal frozen schedule')
            require(row.get('status') == 'COMPLETE' and row.get('validated') is True
                    and row.get('run_id') == run_id
                    and row.get('freeze_sha256') == hashes['freeze'],
                    'Observation is failed, unvalidated or has changed provenance')
            identity = row['observation_id']
            require(identity not in identities, 'Duplicate observation ID')
            identities.add(identity)
            actual_count += 1
    require(actual_count == count, 'Observation ledger has missing physical rows')
    return freeze, paths, hashes


def verify_results(run_id, expected_summary, expected_provenance, input_hashes, freeze):
    prefix = 'experiments/core_rebuild/results/' + run_id
    summary_rel, provenance_rel = prefix + '/summary.json', prefix + '/analysis_provenance.json'
    summary_sha = checked(summary_rel, expected_summary)
    provenance_sha = checked(provenance_rel, expected_provenance)
    summary, provenance = read_json(summary_rel), read_json(provenance_rel)
    require(summary.get('schema') == 'CORE_SUMMARY_V1'
            and provenance.get('schema') == 'CORE_ANALYSIS_PROVENANCE_V1'
            and summary.get('status') == provenance.get('status') == 'COMPLETE'
            and summary.get('run_id') == provenance.get('run_id') == run_id,
            'Summary/provenance identity is incomplete or changed')
    require(summary.get('input_sha256') == provenance.get('input_sha256') == input_hashes,
            'Results do not refer to the verified freeze/raw/report inputs')
    require(summary.get('condition_count') == len(freeze['conditions'])
            == len(summary['conditions']) and summary.get('tier') == freeze['tier'],
            'Result condition matrix differs from freeze')
    require(set(summary['conditions']) == {c['condition_id'] for c in freeze['conditions']},
            'Result condition identities differ from freeze')
    require(all(c.get('status') == 'COMPLETE' and len(c['sessions']) == 10
                for c in summary['conditions'].values()), 'A result condition is incomplete')
    require(set(provenance['output_sha256']) == RESULT_NAMES,
            'Result closure differs from the six frozen analysis outputs')
    closure = {provenance_rel: provenance_sha}
    for name in sorted(RESULT_NAMES):
        relative = prefix + '/' + name
        closure[relative] = checked(relative, provenance['output_sha256'][name])
    require(closure[summary_rel] == summary_sha, 'Summary digest differs across expected/provenance pins')
    expected_scripts = {'experiments/core_rebuild/scripts/' + name for name in SCRIPT_NAMES}
    require(set(summary['analysis_source_sha256']) == set(provenance['analysis_source_sha256'])
            == expected_scripts, 'Result analysis-source closure changed')
    for relative in expected_scripts:
        pin = freeze_source_pin(freeze, relative)
        require(summary['analysis_source_sha256'][relative]
                == provenance['analysis_source_sha256'][relative] == pin,
                'Result analysis source differs from freeze: ' + relative)
    return closure


def copy_checked(root, relative, expected):
    """Copy exact bytes into the new root, checking the copy against its pin."""
    source = source_file(relative)
    destination = root.joinpath(*PurePosixPath(relative).parts)
    require(destination.resolve().is_relative_to(root.resolve()), 'Destination escapes new root')
    destination.parent.mkdir(parents=True, exist_ok=True)
    copied = hashlib.sha256()
    with source.open('rb') as reader, destination.open('xb') as writer:
        for block in iter(lambda: reader.read(1024 * 1024), b''):
            writer.write(block)
            copied.update(block)
    require(copied.hexdigest() == expected, 'Source changed while copying: ' + relative)
    require(sha(destination) == expected, 'Destination copy integrity mismatch: ' + relative)


def generated_bundle(root, directory, manifest_name, names):
    manifest = directory / manifest_name
    metadata = json.loads(manifest.read_text(encoding='utf-8'))
    require(metadata.get('status') == 'COMPLETE' and set(metadata['output_sha256']) == names,
            'Generated output bundle is incomplete')
    digests = {str(manifest.relative_to(root)).replace('\\', '/'): sha(manifest)}
    for name in sorted(names):
        path = directory / name
        digest = digest_text(metadata['output_sha256'][name], 'Generated output ' + name)
        require(path.is_file() and sha(path) == digest, 'Generated output integrity mismatch: ' + name)
        digests[str(path.relative_to(root)).replace('\\', '/')] = digest
    return metadata, digests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('route', choices=('analyze', 'redraw'))
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output-root', type=Path, required=True,
                        help='Explicit new root; it and all copied outputs must not already exist')
    parser.add_argument('--freeze-sha256', required=True)
    parser.add_argument('--observations-sha256', help='Required for analyze; exact published formal ledger digest')
    parser.add_argument('--formal-report-sha256', help='Required for analyze; exact published formal report digest')
    parser.add_argument('--summary-sha256', help='Required for redraw; exact published summary digest')
    parser.add_argument('--analysis-provenance-sha256',
                        help='Required for redraw; exact published analysis-provenance digest')
    args = parser.parse_args()
    require(re.fullmatch(r'[A-Za-z0-9_-]+', args.run_id), 'Run ID must be one safe directory component')
    require(not (ROOT / 'experiments/measurement.lock').exists(),
            'A measurement lock exists; do not reproduce during measurement')
    output = args.output_root.absolute()
    require(not os.path.lexists(output), 'Output root already exists; refusing overwrite')
    require(output.parent.is_dir(), 'Output root parent must already exist')
    require(output.parent.resolve() == output.parent, 'Output root parent is a symlink/alias')
    expected_freeze = digest_text(args.freeze_sha256, 'Freeze digest')
    if args.route == 'analyze':
        require(args.observations_sha256 and args.formal_report_sha256,
                'analyze requires --observations-sha256 and --formal-report-sha256')
        require(not args.summary_sha256 and not args.analysis_provenance_sha256,
                'Result digests belong to the redraw route')
    else:
        require(args.summary_sha256 and args.analysis_provenance_sha256,
                'redraw requires --summary-sha256 and --analysis-provenance-sha256')
        require(not args.observations_sha256 and not args.formal_report_sha256,
                'redraw verifies formal inputs against the pinned result input hashes')
    freeze, paths, hashes = verify_formal(args.run_id, expected_freeze,
                                         args.observations_sha256, args.formal_report_sha256)
    closure = {}
    scripts = SCRIPT_NAMES if args.route == 'analyze' else ('common.py', 'plots.py')
    for name in scripts:
        relative = 'experiments/core_rebuild/scripts/' + name
        closure[relative] = checked(relative, freeze_source_pin(freeze, relative))
    if args.route == 'analyze':
        closure.update({paths[name]: hashes[name] for name in paths})
    else:
        closure.update(verify_results(args.run_id, args.summary_sha256,
                                      args.analysis_provenance_sha256, hashes, freeze))
    # All source validation precedes creation. The exclusive mkdir also rejects
    # a concurrently created destination; an interrupted tree is left intact.
    output.mkdir(exist_ok=False)
    request = {'schema': 'CORE_PORTABLE_REPRODUCTION_REQUEST_V1', 'route': args.route,
               'run_id': args.run_id, 'wrapper_sha256': sha(Path(__file__).resolve()),
               'verified_formal_input_sha256': hashes, 'copied_closure_sha256': closure,
               'native_executions': 0, 'historical_inputs': 0,
               'source_inputs_modified': False, 'existing_outputs_overwritten': False}
    write_new(output / 'reproduction_request.json', request)
    result = {'schema': 'CORE_PORTABLE_REPRODUCTION_RESULT_V1', 'route': args.route,
              'run_id': args.run_id, 'status': 'INCOMPLETE', 'source_inputs_modified': False,
              'native_executions': 0, 'bootstrap_requested': args.route == 'analyze',
              'bootstrap_resamples_per_condition': 10000 if args.route == 'analyze' else 0}
    try:
        for relative, expected in sorted(closure.items()):
            copy_checked(output, relative, expected)
        runtime = output / 'runtime'
        runtime.mkdir()
        temporary, mpl_config = runtime / 'tmp', runtime / 'matplotlib'
        temporary.mkdir()
        mpl_config.mkdir()
        environment = dict(os.environ, TMPDIR=str(temporary), TMP=str(temporary),
                           TEMP=str(temporary), MPLCONFIGDIR=str(mpl_config),
                           MPLBACKEND='Agg', PYTHONDONTWRITEBYTECODE='1')
        copied_core = output / 'experiments/core_rebuild'
        if args.route == 'analyze':
            command = [sys.executable, '-B', str(copied_core / 'scripts/summarize.py'),
                       '--run-id', args.run_id, '--freeze-sha256', hashes['freeze']]
        else:
            command = [sys.executable, '-B', str(copied_core / 'scripts/plots.py'),
                       '--run-id', args.run_id, '--summary-sha256',
                       digest_text(args.summary_sha256, 'Summary digest')]
        result['command'] = command
        result['runtime_paths'] = {'TMPDIR': 'runtime/tmp', 'MPLCONFIGDIR': 'runtime/matplotlib'}
        with (output / 'reproduction.log').open('xb') as log:
            process = subprocess.run(command, cwd=output, env=environment,
                                     stdout=log, stderr=subprocess.STDOUT, check=False)
        result['returncode'] = process.returncode
        require(process.returncode == 0, 'Frozen reproduction command failed; retain the new tree and log')
        generated_directory = copied_core / 'results' / args.run_id
        if args.route == 'analyze':
            generated, result['output_sha256'] = generated_bundle(
                output, generated_directory, 'analysis_provenance.json', RESULT_NAMES)
            require(generated['input_sha256'] == hashes, 'Generated analysis input identity differs')
        else:
            generated, result['output_sha256'] = generated_bundle(
                output, generated_directory / 'figures', 'figure_provenance.json', FIGURE_NAMES)
            require(generated['summary_sha256'] == digest_text(args.summary_sha256, 'Summary digest'),
                    'Generated figures refer to a different summary')
        result['log_sha256'] = sha(output / 'reproduction.log')
        # Frozen subprocesses must only read the copied closure. Record source
        # integrity again without rewriting either source or copied evidence.
        for relative, expected in closure.items():
            require(sha(source_file(relative)) == expected, 'Original closure changed: ' + relative)
            require(sha(output.joinpath(*PurePosixPath(relative).parts)) == expected,
                    'Copied input changed: ' + relative)
        result['status'] = 'COMPLETE'
    except BaseException as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        write_new(output / 'reproduction_result.json', result)
    print(json.dumps({'status': result['status'], 'route': args.route,
                      'output_root': str(output), 'error': result.get('error')}))
    return 0 if result['status'] == 'COMPLETE' else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({'status': 'REJECTED', 'type': type(error).__name__,
                          'message': str(error)}), file=sys.stderr)
        raise SystemExit(2)
