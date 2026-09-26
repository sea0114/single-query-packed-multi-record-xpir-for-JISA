#!/usr/bin/env python3
"""Replay archived B1/B2-B with their original pure analysis functions.

No native execution; no writes outside a new output directory. Never calls old
report/runner CLIs. Historical inference is preserved, not replaced by diagnostics.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib
import json
import math
from pathlib import Path
import random
import statistics
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / 'artifact/results/historical_replay'
PINS = {
    'revision_notes/B0_benchmark_manifest.json': '69c130a37990ce1262292476b29f6b365974ecdbe383df0511b66822f5e3bd6e',
    'revision_notes/B2_B_freeze_manifest.json': 'b92848c888bd7f74113e0182bade7b4aed5e4e1d83960941170d7c2e25593e71',
    'revision_notes/B1_primary_logs/task_rows.jsonl': 'd96aa0d7f53c00ff895e9368f96ae563476b49c74331144cfeee73e6ecccf6ef',
    'revision_notes/B1_primary_logs/raw_rows.jsonl': 'd5e91c0c534c1a5e733308889dd013dda68f7c3730007c96accbf99fc2d1e41b',
    'revision_notes/B2_B_execution/task_rows.jsonl': 'fe4fe3db4c400a9b456f9b258c3fa45c5acb5ee5d6f52caa78105eeb9d0d4f85',
    'revision_notes/B2_B_execution/worker_rows.jsonl': '5fdca1b674a048ceb396e06a437bc48e1460b183d1d169ba8b80e82857475cfc',
    'revision_notes/B2_B_execution/B2_B_raw_dataset.jsonl': '94b50b2a417d7a3894c5f57c1a7ab668c5464ff0db74865bdbf83b64f76392d0',
    'tools/benchmark/analysis.py': '56e0204c989ee0916e9afe0d3946737434f4e23bcb67e28ca74e145503a56d9c',
    'tools/benchmark/spec.py': '70bae995b8050753f2958e10c4fcba3d22616beac1488b71eabd0be0e7960861',
    'tools/benchmark/b1_report.py': '92a01856e9f59b49f449a895770192f928dbe9dd01decc76145e69b4e4b16224',
    'tools/b2b/b2b_analyze.py': '69d52e268feb52a3e025941529894df70c0c80d49647fda2945bfcbf79ea9de4',
    'tools/b2b/b2b_common.py': '05bb403c80951d4d7bd09e3d4ce465aaa7c40f87efb1fc6922518a63e35dee9a',
    'revision_notes/B0_run_schedule.json': '07925546f8a3a7b42d8e78ad4ee3ef3698ab075d6c8e681a2ca8a3fb802f6d30',
    'revision_notes/B2_B_run_schedule.json': 'dbdac6d991413b4ecb723455141d932ed6fb2f0f1d8bbdaaf97492d927294025',
}


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8-sig'))


def jsonl(path):
    return [json.loads(line) for line in (ROOT / path).read_text(encoding='utf-8-sig').splitlines() if line.strip()]


def quantile(values, p):
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    left = math.floor(position)
    return ordered[left] + (ordered[min(left + 1, len(ordered) - 1)] - ordered[left]) * (position - left)


def describe(values):
    if not values:
        return {'n': 0, 'median': None, 'Q1': None, 'Q3': None, 'min': None, 'max': None}
    return dict(n=len(values), median=statistics.median(values), Q1=quantile(values, .25),
                Q3=quantile(values, .75), min=min(values), max=max(values))


def median_claim_evidence(packed, repeated):
    if len(packed) != len(repeated) or not packed or any(x <= 0 for x in packed):
        raise ValueError('Complete positive paired times required')
    ratios = [b / a for a, b in zip(packed, repeated)]
    reductions = [1 - a / b for a, b in zip(packed, repeated)]
    return dict(median_paired_ratio=statistics.median(ratios),
                packed_separate_median_ns=statistics.median(packed),
                repeated_separate_median_ns=statistics.median(repeated),
                packed_separate_median_lower=statistics.median(packed) < statistics.median(repeated),
                ratio_of_separate_medians=statistics.median(repeated) / statistics.median(packed),
                median_pair_reduction_relative_to_repeated=statistics.median(reductions),
                transform_of_median_ratio=1 - 1 / statistics.median(ratios),
                reduction_note='Median of per-pair reductions is computed directly; even-sample medians need not commute with nonlinear transformation.')


def differences(expected, actual, path=''):
    """Exact comparisons: never hide estimator/RNG changes behind a tolerance."""
    if expected == actual:
        return []
    if isinstance(expected, dict) and isinstance(actual, dict):
        result = []
        for key in sorted(set(expected) | set(actual)):
            if key not in expected or key not in actual:
                result.append(dict(path=path + '/' + str(key), reason='missing key'))
            else:
                result.extend(differences(expected[key], actual[key], path + '/' + str(key)))
        return result
    if isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual):
        result = []
        for i, (a, b) in enumerate(zip(expected, actual)):
            result.extend(differences(a, b, path + '/' + str(i)))
        return result
    return [dict(path=path, expected=expected, recomputed=actual)]


def cell_key(stage, row):
    if stage == 'B1':
        w = row['workload']
        return stage, 2, w['N'], w['ell_bits'], w['rho_0'], row['preprocess_mode']
    return stage, row['alpha'], row['N'], row['ell_bits'], row['rho_0'], row['view']


def identity(key):
    return dict(zip(('experiment_id', 'alpha', 'N', 'ell_bits', 'rho0', 'view'), key))


def correlation(x, y):
    if len(x) < 2:
        return None
    xm, ym = statistics.mean(x), statistics.mean(y)
    denominator = math.sqrt(sum((v - xm)**2 for v in x) * sum((v - ym)**2 for v in y))
    return sum((a - xm) * (b - ym) for a, b in zip(x, y)) / denominator if denominator else None


def account(stage, tasks, workers, schedule):
    expected = {(e['run_id'], e['pair_id'], e['method']) for e in schedule} if stage == 'B1' else {
        (e['pair_id'] + '_' + method, e['pair_id'], method) for e in schedule for method in e['method_order']}
    assert len(tasks) == len(expected)
    assert {(r['run_id'], r['pair_id'], r['method']) for r in tasks} == expected
    assert len({r['run_id'] for r in tasks}) == len(tasks)
    assert len({r['run_id'] for r in workers}) == len(workers)
    by_parent = defaultdict(list)
    for worker in workers:
        by_parent[worker['parent_run_id']].append(worker)
    pairs = defaultdict(dict)
    for task in tasks:
        assert task['status'] == 'COMPLETE' and task['output_verified']
        assert task['method'] not in pairs[task['pair_id']]
        pairs[task['pair_id']][task['method']] = task
        ws = by_parent[task['run_id']]
        alpha = 2 if stage == 'B1' else task['alpha']
        assert len(ws) == (1 if task['method'] == 'packed' else alpha)
        assert set(task['worker_ids']) == {w['run_id'] for w in ws}
        assert task['task_start_ns'] == min(w['task_start_ns'] for w in ws)
        assert task['task_end_ns'] == max(w['task_end_ns'] for w in ws)
        assert task['task_total_ns'] == task['task_end_ns'] - task['task_start_ns']
        assert task['aggregate_cpu_ns'] == sum(w['cpu_user_ns'] + w['cpu_system_ns'] for w in ws)
        assert len({w['key_fingerprint'] for w in ws}) == len(ws)
        for w in ws:
            assert w['status'] == 'COMPLETE' and w['output_verified']
            assert w['actual_hex'] == w['expected_hex']
            assert w['task_total_ns'] == w['task_end_ns'] - w['task_start_ns']
            assert w['phase_events']['ValidationOverhead']['begin'] >= task['task_end_ns']
            for phase, event in w['phase_events'].items():
                assert event['end'] - event['begin'] == w['phase_ns'][phase]
    for pair in pairs.values():
        assert set(pair) == {'packed', 'repeated'}
        assert cell_key(stage, pair['packed']) == cell_key(stage, pair['repeated'])
        assert pair['packed']['warmup'] == pair['repeated']['warmup']
        assert pair['packed']['target_tuple'] == pair['repeated']['target_tuple']
        if stage == 'B1':
            assert pair['packed']['db_fixture_hash'] == pair['repeated']['db_fixture_hash']
        else:
            db_hashes = {w['db_fixture_hash'] for t in pair.values() for w in by_parent[t['run_id']]}
            assert len(db_hashes) == 1
    return pairs, by_parent, dict(task_rows=len(tasks), worker_rows=len(workers), pairs=len(pairs),
        warmup_tasks=sum(r['warmup'] for r in tasks), measured_tasks=sum(not r['warmup'] for r in tasks),
        task_status=dict(Counter(r['status'] for r in tasks)), worker_status=dict(Counter(r['status'] for r in workers)),
        duplicate_or_missing_pairs=0, failed=0, incomplete=0, excluded_outliers=0, imputed=0,
        retries=0, schedule_accounting='EXACT', endpoint_and_worker_accounting='PASS',
        persisted_session_id=False, persisted_block_id=False,
        session_semantics='One archived execution batch; rounds/repetition are available, not independent sessions.')


def derive(stage, pairs, by_parent, historical_cells):
    groups = defaultdict(list)
    for pair in pairs.values():
        groups[cell_key(stage, pair['packed'])].append(pair)
    cells, normalized, diagnostics, phases = [], [], [], []
    for key, group in sorted(groups.items()):
        group.sort(key=lambda p: min(t['task_start_ns'] for t in p.values()))
        measured = [p for p in group if not p['packed']['warmup']]
        packed = [p['packed']['task_total_ns'] for p in measured]
        repeated = [p['repeated']['task_total_ns'] for p in measured]
        ratios = [b / a for a, b in zip(packed, repeated)]
        claims = median_claim_evidence(packed, repeated)
        historical = historical_cells[key]
        assert claims['median_paired_ratio'] == historical['median_paired_ratio']
        base = identity(key)
        cells.append({**base, 'n_warmup_pairs': len(group) - len(measured), 'n_measured_pairs': len(measured),
                      'n_failed_pairs': 0, 'n_incomplete_pairs': 0, 'CI95': historical['CI95'],
                      'bootstrap_seed': historical['seed'], 'bootstrap_resamples': 10000,
                      'packed_TaskTotal_ns': describe(packed), 'repeated_TaskTotal_ns': describe(repeated),
                      'separate_median_evidence': claims})
        ordered_groups = defaultdict(list)
        for index, p in enumerate(measured):
            first = min(p.values(), key=lambda t: t['task_start_ns'])['method']
            ordered_groups[first].append(repeated[index] / packed[index])
            for method in ('packed', 'repeated'):
                t = p[method]
                normalized.append({**base, 'contract_id': 'B0-1.1' if stage == 'B1' else 'B2B-1.0',
                    'pair_id': t['pair_id'], 'batch_id': t['batch_id'], 'session_id': None, 'block_id': None,
                    'round_index': t['repetition'], 'task_ordinal': t['ordinal'], 'method_order': first + '_first',
                    'method': method, 'run_id': t['run_id'], 'start_ns': t['task_start_ns'],
                    'end_ns': t['task_end_ns'], 'task_total_ns': t['task_total_ns'], 'status': t['status'],
                    'validation_passed': t['output_verified'], 'binary_sha256': t.get('build_hash', t.get('binary_sha256'))})
        middle = len(measured) // 2
        diagnostics.append({**base, 'batch_id': measured[0]['packed']['batch_id'], 'n_original_sessions': None,
            'method_order_counts': {k: len(v) for k, v in ordered_groups.items()},
            'ratio_by_first_method': {k: describe(v) for k, v in ordered_groups.items()},
            'first_chronological_half_ratios': describe(ratios[:middle]),
            'second_chronological_half_ratios': describe(ratios[middle:]),
            'lag1_ratio_correlation_descriptive': correlation(ratios[:-1], ratios[1:]),
            'first_measured_start_ns': min(t['task_start_ns'] for t in measured[0].values()),
            'last_measured_end_ns': max(t['task_end_ns'] for t in measured[-1].values()),
            'interpretation': 'Descriptive order/drift diagnostics only. Post-hoc halves are not sessions. No independence, CI coverage, or causal test is inferred.'})
        for method in ('packed', 'repeated'):
            phase_names = list(measured[0][method]['phase_ns'])
            phase_work = {name: [] for name in phase_names}
            phase_envelope = {name: [] for name in phase_names}
            final_worker_spans, start_skews = [], []
            for p in measured:
                t = p[method]
                ws = by_parent[t['run_id']]
                latest = max(ws, key=lambda w: w['task_end_ns'])
                final_worker_spans.append(latest['task_total_ns'])
                start_skews.append(max(w['task_start_ns'] for w in ws) - min(w['task_start_ns'] for w in ws))
                for name in phase_names:
                    phase_work[name].append(sum(w['phase_ns'][name] for w in ws))
                    phase_envelope[name].append(max(w['phase_events'][name]['end'] for w in ws) - min(w['phase_events'][name]['begin'] for w in ws))
            phases.append({**base, 'method': method,
                'aggregate_worker_phase_duration_ns': {k: describe(v) for k, v in phase_work.items()},
                'phase_first_begin_to_last_end_ns': {k: describe(v) for k, v in phase_envelope.items()},
                'last_finishing_worker_task_span_ns': describe(final_worker_spans),
                'worker_start_skew_ns': describe(start_skews),
                'interpretation': 'Phase envelopes may overlap and include gaps; neither their sum nor aggregate worker durations is TaskTotal. ONLINE server preprocessing and all validation remain outside TaskTotal. No causal attribution.'})
    return cells, normalized, diagnostics, phases


def run(output):
    output = output.resolve()
    if not output.is_relative_to((ROOT / 'artifact/results').resolve()):
        raise ValueError('Output must be a new directory under artifact/results')
    if output.exists():
        raise FileExistsError('Refusing to overwrite derived evidence; choose a fresh --out directory')
    tracked = dict(PINS)
    for name, expected in PINS.items():
        assert sha(ROOT / name) == expected, 'Pinned input mismatch: ' + name
    m1, m2 = read('revision_notes/B0_benchmark_manifest.json'), read('revision_notes/B2_B_freeze_manifest.json')
    # Verify all original imported local dependencies before executing any analysis.
    for name, expected in m1['frozen_files'].items():
        if name.startswith('tools/benchmark/') and name.endswith('.py'):
            assert sha(ROOT / name) == expected, name
            tracked[name] = expected
    for name, expected in m2['source_tool_hashes'].items():
        if name.endswith('.py'):
            assert sha(ROOT / name) == expected, name
            tracked[name] = expected
    for name, expected in read('revision_notes/B1_primary_logs/preregistration.json')['tool_hashes'].items():
        assert sha(ROOT / name) == expected, name
        tracked[name] = expected
    assert read('revision_notes/B1_primary_logs/batch_status.json')['environment_valid']
    assert read('revision_notes/B2_B_execution/environment_validation.json')['environment_valid']
    t1 = jsonl('revision_notes/B1_primary_logs/task_rows.jsonl')
    w1 = [r for r in jsonl('revision_notes/B1_primary_logs/raw_rows.jsonl') if r['record_type'] == 'worker']
    t2 = jsonl('revision_notes/B2_B_execution/task_rows.jsonl')
    w2 = jsonl('revision_notes/B2_B_execution/worker_rows.jsonl')
    s1, s2 = read('revision_notes/B0_run_schedule.json'), read('revision_notes/B2_B_run_schedule.json')
    p1, b1w, count1 = account('B1', t1, w1, s1)
    p2, b2w, count2 = account('B2B', t2, w2, s2)
    sys.path.insert(0, str(ROOT / 'tools/benchmark'))
    b1_report = importlib.import_module('b1_report')
    result1 = b1_report.build_results(m1, t1, True)
    sys.path.insert(0, str(ROOT / 'tools/b2b'))
    b2_analyze = importlib.import_module('b2b_analyze')
    result2 = b2_analyze.analyze(t2, s2, PINS['revision_notes/B2_B_freeze_manifest.json'], {'environment_valid': True})
    targets = {
        'revision_notes/B1_primary_point_results.json': result1['points'],
        'revision_notes/B1_primary_ratio_results.json': result1['ratios'],
        'revision_notes/B1_primary_logs/paired_ratio.json': result1['paired_rows'],
        'revision_notes/B1_primary_logs/bootstrap_results.json': result1['bootstrap'],
        'revision_notes/B1_primary_logs/analysis.json': {k: v for k, v in result1.items() if k not in ('points', 'paired_rows', 'bootstrap')},
        'revision_notes/B2_B_execution/analysis_frozen.json': result2,
    }
    comparison = []
    for path, result in targets.items():
        tracked[path] = sha(ROOT / path)
        diff = differences(read(path), result)
        comparison.append(dict(path=path, status='EXACT_MATCH' if not diff else 'DIFFERENCE', differences=diff))
    old = {}
    for c in result1['ratios']:
        old['B1', 2, c['N'], c['ell_bits'], c['rho_0'], c['mode']] = c
    for c in result2['cells']:
        r = c['paired_completed_task_ratio']
        old['B2B', c['alpha'], c['N'], c['ell_bits'], 8, c['view']] = dict(median_paired_ratio=r['median'], CI95=r['CI95'], seed=r['seed'])
    d1, n1, g1, ph1 = derive('B1', p1, b1w, old)
    d2, n2, g2, ph2 = derive('B2B', p2, b2w, old)
    cells = d1 + d2
    lookup = {(c['experiment_id'], c['alpha'], c['N'], c['ell_bits'], c['rho0'], c['view']): c for c in cells}
    overlaps = []
    historical_overlap = read('revision_notes/B2_B_result_audit/B1_B2B_sanity_details.json')
    for ref in historical_overlap['rows']:
        first = lookup['B1', 2, ref['N'], ref['ell_bits'], 8, ref['view']]
        second = lookup['B2B', 2, ref['N'], ref['ell_bits'], 8, ref['view']]
        for prefix, c in [('B1', first), ('B2B', second)]:
            assert ref[prefix + '_median_R'] == c['separate_median_evidence']['median_paired_ratio']
            assert ref[prefix + '_CI95'] == c['CI95']
            assert ref[prefix + '_pairs'] == c['n_measured_pairs']
            for method in ('packed', 'repeated'):
                assert ref[method][prefix + '_TaskTotal_median_ns'] == c[method + '_TaskTotal_ns']['median']
        overlaps.append(dict(N=ref['N'], ell_bits=ref['ell_bits'], view=ref['view'], B1=first, B2B=second,
                             provenance='Extends existing B1_B2B_sanity_details.json; no pooling or causal test.'))
    additional = [
        'revision_notes/B1_primary_logs/batch_status.json', 'revision_notes/B1_primary_logs/analysis_invocation.json',
        'revision_notes/B1_primary_logs/preregistration.json',
        'revision_notes/B1_primary_logs/environment_start.json', 'revision_notes/B1_primary_logs/environment_end.json',
        'revision_notes/B2_B_execution/environment_validation.json', 'revision_notes/B2_B_execution/environment_start.json',
        'revision_notes/B2_B_execution/environment_end.json', 'revision_notes/B2_B_execution/postprocess_corrections.json',
        'revision_notes/B2_B_result_audit/B1_B2B_sanity_details.json', 'revision_notes/B2_B_execution/raw_dataset_provenance.json',
    ]
    for path in additional:
        tracked[path] = sha(ROOT / path)
    input_index = [dict(path=k, bytes=(ROOT / k).stat().st_size, sha256=v) for k, v in sorted(tracked.items())]
    exact = all(c['status'] == 'EXACT_MATCH' for c in comparison)
    versions = dict(python=sys.version, executable=sys.executable, platform=sys.platform,
        historical_python='3.12.3 (main, Nov 6 2024, 18:32:19) [GCC 13.2.0]',
        matched_historical_python=sys.version_info[:3] == (3, 12, 3),
        algorithm='Original hash-verified pure functions; random.Random.choices, statistics.median, Type-7 percentiles; original ordered pairs; seed reset per cell.',
        modules={module.__name__: {'path': module.__file__, 'sha256': sha(module.__file__)} for module in
                 (random, statistics, b1_report, b2_analyze, sys.modules['analysis'], sys.modules['spec'],
                  sys.modules['b1_common'], sys.modules['b2b_common'], sys.modules['b2b_schema'])},
        command_argv=sys.argv, script_sha256=sha(__file__))
    summary = dict(status='PASS' if exact else 'FAIL', native_measurements=0, original_pipeline_replay=True,
        exact_comparison_targets=len(comparison), exact_match_targets=sum(c['status'] == 'EXACT_MATCH' for c in comparison),
        difference_count=sum(len(c['differences']) for c in comparison), B1=count1, B2B=count2,
        cells=len(cells), median_and_CI_values_reproduced=3 * len(cells),
        B1_bootstrap_samples_compared_exactly=96 * 10000,
        separate_median_packed_lower_by_stage={stage: sum(c['separate_median_evidence']['packed_separate_median_lower'] for c in cells if c['experiment_id'] == stage) for stage in ('B1', 'B2B')},
        separate_median_claim_scope='Independent computation from real task rows; not implied by median paired ratio.',
        confidence_scope='Historical pointwise pair-bootstrap replay. Does not establish iid observations, advertised coverage under temporal dependence, simultaneous coverage, or cross-session generalization.',
        monitoring_trace='UNAVAILABLE; retained endpoint/lifetime resource observations are not 10 ms traces.',
        sessions='No original independent session IDs; method-order/chronological diagnostics remain descriptive.',
        outlier_deletion=False, retries=False, imputation=False, cross_stage_pooling=False)
    output.mkdir(parents=True)
    def write(name, value):
        with (output / name).open('x', encoding='utf-8', newline='\n') as handle:
            if isinstance(value, str):
                handle.write(value)
            else:
                json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write('\n')
    write('status.json', summary)
    write('versions.json', versions)
    write('input_index.json', input_index)
    write('exact_comparisons.json', comparison)
    write('cells.json', cells)
    write('method_order_chronological_diagnostics.json', g1 + g2)
    write('phase_endpoint_diagnostics.json', ph1 + ph2)
    write('overlap_eight_cells.json', overlaps)
    with (output / 'normalized_measured_tasks.jsonl').open('x', encoding='utf-8', newline='\n') as handle:
        for row in n1 + n2:
            handle.write(json.dumps(row, sort_keys=True) + '\n')
    flat = []
    for c in cells:
        claim = c['separate_median_evidence']
        flat.append({**{k: c[k] for k in ('experiment_id', 'alpha', 'N', 'ell_bits', 'rho0', 'view', 'n_warmup_pairs', 'n_measured_pairs', 'n_failed_pairs', 'n_incomplete_pairs')},
            'median_paired_ratio': claim['median_paired_ratio'], 'CI95_low': c['CI95'][0], 'CI95_high': c['CI95'][1],
            **{method + '_TaskTotal_ns_' + stat: c[method + '_TaskTotal_ns'][stat] for method in ('packed', 'repeated') for stat in ('median', 'Q1', 'Q3', 'min', 'max')},
            'packed_separate_median_lower': claim['packed_separate_median_lower'],
            'median_pair_reduction_relative_to_repeated': claim['median_pair_reduction_relative_to_repeated']})
    with (output / 'cells.csv').open('x', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)
    write('replay_report.md', '# P1：歷史重算\n\n'
        + f"狀態：{summary['status']}。以 hash 核對原分析純函式，{len(cells)} cells 的估計量及 CI、absolute summaries 與原輸出作精確比較；{summary['difference_count']} 個差異。未執行 native benchmark。\n\n"
        + 'B1 2,160 measured pairs／96 cells；B2-B 240 measured pairs／24 cells。Warmups 分別 288／72 pairs；全部 tasks/workers COMPLETE，schedule/配對/endpoint/validation accounting 通過。沒有 retry、outlier deletion、imputation 或混池。\n\n'
        + f"另由 raw data 直接核對 separate medians：B1 {summary['separate_median_packed_lower_by_stage']['B1']}/96、B2-B {summary['separate_median_packed_lower_by_stage']['B2B']}/24 的 packed separate median 較低。此結果不由 median paired ratio > 1 推導；單元測試保存反例。\n\n"
        + 'exact_comparisons.json 保存全部比較結果；cells.csv/json 保存 120 cells 完整數值；overlap_eight_cells.json 延伸既有八列 comparison 的 absolute summaries。method_order_chronological_diagnostics.json 只作描述性診斷，不能用以證明 iid 或原 CI 的 coverage。原資料沒有預先定義 independent sessions；不得把事後 halves 當 sessions，10,000 resamples 不增加 measured n。\n\n'
        + 'phase_endpoint_diagnostics.json 取自實際 worker phase begin/end；phase envelopes 可重疊且包含 gaps，phase sums 與 envelopes 的總和均不是 concurrent TaskTotal。ONLINE preprocessing 與 validation 不在 TaskTotal 內。尚未據此建立 historical gap 的唯一因果來源。\n\n'
        + '歷史 10 ms monitor traces 未保存，仍為 unavailable。重算不能補回 frequency/thermal history 或同步 RSS peaks。安全性與 native/formal sampler bridge 不由本分析建立。\n')
    assert all(sha(ROOT / name) == value for name, value in tracked.items()), 'Input mutation detected'
    write('output_manifest.json', dict(schema='M1_M7_P1_DERIVED_V1', historical_inputs_unchanged=True,
        artifacts=[dict(path=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(output.iterdir()) if p.is_file()]))
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if exact else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    raise SystemExit(run(args.out))
