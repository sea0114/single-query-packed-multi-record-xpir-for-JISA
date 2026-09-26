#!/usr/bin/env python3
"""Frozen descriptive B3 analysis; no bootstrap, p-values, or historical pooling.

Rows are matched to the frozen schedule. Partial/failing/unstarted observations
remain in accounting. A session with an incomplete/failed warmup is withheld
from latency summaries. Synthetic fixtures are accepted only by the explicit
unit-test API, never by the empirical CLI.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
CT = 131072
ANALYSIS_ID = 'B3_DESCRIPTIVE_SESSION_V1'
SCOPE = ('Median paired ratio and pair IQR; observed session medians and their range. '
         'The range is not a confidence interval. No iid, coverage, significance, '
         'historical replication, or unique causal explanation is inferred.')


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def quantile(values, p):
    v = sorted(values)
    location = (len(v) - 1) * p
    left = math.floor(location)
    return v[left] + (v[min(left + 1, len(v) - 1)] - v[left]) * (location - left)


def describe(values):
    if not values:
        return dict(n=0, median=None, Q1=None, Q3=None, IQR=None, min=None, max=None)
    q1, q3 = quantile(values, .25), quantile(values, .75)
    return dict(n=len(values), median=statistics.median(values), Q1=q1, Q3=q3,
                IQR=q3-q1, min=min(values), max=max(values))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def expanded_schedule(config):
    rows = []
    for entry in config['schedule']:
        require(entry['phase'] in ('warmup', 'measured'), 'Unknown schedule phase')
        order = entry.get('method_order', ['packed', 'repeated'])
        require(set(order) == {'packed', 'repeated'} and len(order) == 2, 'Invalid method order')
        methods = [entry['method']] if 'method' in entry else order
        for method in methods:
            rows.append({**entry, 'method': method, 'method_order': order})
    by_key = {(r['pair_id'], r['method']): r for r in rows}
    require(len(by_key) == len(rows), 'Duplicate scheduled task')
    pairs = defaultdict(list)
    for row in rows:
        require(row['method'] in ('packed', 'repeated'), 'Unknown scheduled method')
        pairs[row['pair_id']].append(row)
    for pair in pairs.values():
        require(len(pair) == 2 and {p['method'] for p in pair} == {'packed', 'repeated'}, 'Incomplete scheduled pair')
        require(all(pair[0][k] == pair[1][k] for k in ('cell_id', 'session_id', 'phase', 'method_order')), 'Pair schedule metadata conflict')
    return by_key


def check_payload(cell, task, workers):
    """Check observed native counters against fixed encoding, including L > 1."""
    n, rho, alpha = cell['n'], cell['rho_0'], cell['alpha']
    J = (cell['ell_bits'] + rho - 1) // rho
    L = (J + n - 1) // n
    require(cell['J'] == J and cell['L'] == L and cell['u'] == alpha * J / n, 'Invalid J/L/u')
    require(cell['ciphertext_bytes'] == CT, 'Unexpected ciphertext representation')
    count = 1 if task['method'] == 'packed' else alpha
    require(len(workers) == count, 'Completed task missing worker records')
    require(len({w['worker_index'] for w in workers}) == count, 'Duplicate worker index')
    require(set(w['worker_index'] for w in workers) == set(range(count)), 'Worker indices incomplete')
    for w in workers:
        require(w['status'] == 'COMPLETE' and w['output_verified'] is True, 'Completed task contains invalid worker')
        for key in ('N', 'ell_bits', 'alpha', 'rho_0', 'w', 'J', 'L'):
            require(w[key] == cell[key], 'Worker layout mismatch: ' + key)
        require(w['query_ciphertexts'] == cell['N'] and w['reply_ciphertexts'] == L, 'Worker reply/query count mismatch')
        require(w['query_payload_bytes'] == cell['N'] * CT and w['reply_payload_bytes'] == L * CT, 'Worker payload mismatch')
        require(w['task_total_ns'] == w['task_end_ns'] - w['task_start_ns'] > 0, 'Worker endpoint mismatch')
    require(task['task_start_ns'] == min(w['task_start_ns'] for w in workers), 'Parent start mismatch')
    require(task['task_end_ns'] == max(w['task_end_ns'] for w in workers), 'Parent end mismatch')
    require(task['task_total_ns'] == task['task_end_ns'] - task['task_start_ns'] > 0, 'Parent TaskTotal mismatch')
    for key in ('query_ciphertexts', 'reply_ciphertexts', 'query_payload_bytes', 'reply_payload_bytes'):
        require(task[key] == sum(w[key] for w in workers), 'Parent observed counter mismatch: ' + key)
    require(task['query_ciphertexts'] == count * cell['N'] and task['reply_ciphertexts'] == count * L, 'Task ciphertext count mismatch')
    return dict(method=task['method'], worker_count=count, J=J, L=L, u=alpha*J/n,
                query_ciphertexts=task['query_ciphertexts'], reply_ciphertexts=task['reply_ciphertexts'],
                query_payload_bytes=task['query_payload_bytes'], reply_payload_bytes=task['reply_payload_bytes'])


def analyze(config, tasks, workers, config_sha256, *, synthetic=False):
    expected = expanded_schedule(config)
    cells = {c['cell_id']: c for c in config['cells']}
    require(len(cells) == len(config['cells']), 'Duplicate cell')
    require(all(e['cell_id'] in cells for e in expected.values()), 'Schedule references undefined cell')
    allowed_label = 'SYNTHETIC_UNIT_ONLY' if synthetic else 'B3_FORMAL'
    if synthetic:
        require(config.get('synthetic_fixture') is True, 'Synthetic config marker required')
    else:
        require(not config.get('synthetic_fixture'), 'Empirical analysis rejects synthetic config')
    task_map, worker_map = {}, defaultdict(list)
    for row in tasks + workers:
        require(row.get('timing_label') == allowed_label, 'Reject pilot, foreign, or synthetic timing rows')
        require(row.get('experiment_id') == 'B3', 'Foreign experiment')
        require(row.get('config_sha256') == config_sha256, 'Mixed or incorrect config hash')
        key = row['pair_id'], row['method']
        require(key in expected, 'Unscheduled observation')
        entry = expected[key]
        cell = cells[entry['cell_id']]
        for field in ('cell_id', 'session_id', 'phase'):
            require(row[field] == entry[field], 'Schedule mismatch: ' + field)
        for field in ('study', 'implementation_id', 'resource_policy_id', 'N', 'ell_bits', 'alpha', 'view'):
            require(row[field] == cell[field], 'Workload mismatch: ' + field)
    for task in tasks:
        key = task['pair_id'], task['method']
        require(task['record_type'] == 'task' and key not in task_map, 'Duplicate/mistyped task')
        task_map[key] = task
    for worker in workers:
        key = worker['pair_id'], worker['method']
        require(worker['record_type'] == 'worker' and key in task_map, 'Orphan/mistyped worker')
        worker_map[key].append(worker)
    measured_rows, session_rows, cell_rows, payload_checks = [], [], [], []
    failure_rows = []
    for key, entry in expected.items():
        row = task_map.get(key)
        if row and row['status'] == 'COMPLETE':
            require(row.get('validation_passed') is True, 'Complete task did not pass validation')
            payload_checks.append({**{k: entry[k] for k in ('cell_id', 'session_id', 'phase', 'pair_id')},
                                   **check_payload(cells[entry['cell_id']], row, worker_map[key])})
        elif row:
            failure_rows.append(dict(pair_id=key[0], method=key[1], cell_id=entry['cell_id'], session_id=entry['session_id'],
                                     phase=entry['phase'], status=row['status'], failure_reason=row.get('failure_reason', '')))
        else:
            failure_rows.append(dict(pair_id=key[0], method=key[1], cell_id=entry['cell_id'], session_id=entry['session_id'],
                                     phase=entry['phase'], status='UNSTARTED', failure_reason='No archived task row'))
    for cell_id, cell in cells.items():
        scheduled = [e for e in expected.values() if e['cell_id'] == cell_id]
        sessions = sorted({e['session_id'] for e in scheduled})
        pooled_ratios, pooled_times = [], {'packed': [], 'repeated': []}
        local_sessions = []
        for session in sessions:
            se = [e for e in scheduled if e['session_id'] == session]
            warm = [e for e in se if e['phase'] == 'warmup']
            measured = [e for e in se if e['phase'] == 'measured']
            warm_valid = bool(warm) and all(task_map.get((e['pair_id'], e['method']), {}).get('status') == 'COMPLETE' for e in warm)
            pair_ids = list(dict.fromkeys(e['pair_id'] for e in measured))
            ratios, times, starts = [], {'packed': [], 'repeated': []}, []
            complete_pair_count = 0
            first_methods = Counter()
            for pair_id in pair_ids:
                pair = {m: task_map.get((pair_id, m)) for m in ('packed', 'repeated')}
                complete = all(r and r['status'] == 'COMPLETE' for r in pair.values())
                complete_pair_count += complete
                if warm_valid:
                    for method, row in pair.items():
                        if row and row['status'] == 'COMPLETE':
                            times[method].append(row['task_total_ns'])
                if not complete:
                    continue
                first = min(pair, key=lambda m: pair[m]['task_start_ns'])
                order = expected[pair_id, 'packed']['method_order']
                require(first == order[0], 'Observed method order disagrees with frozen schedule')
                first_methods[first] += 1
                ratio = pair['repeated']['task_total_ns'] / pair['packed']['task_total_ns']
                record = dict(cell_id=cell_id, study=cell['study'], session_id=session, pair_id=pair_id,
                              method_order=order, ratio=ratio, included_in_latency_summary=warm_valid,
                              packed_ns=pair['packed']['task_total_ns'], repeated_ns=pair['repeated']['task_total_ns'])
                measured_rows.append(record)
                if warm_valid:
                    ratios.append(ratio)
                    starts.append(min(r['task_start_ns'] for r in pair.values()))
            counts = Counter(task_map.get((e['pair_id'], e['method']), {}).get('status', 'UNSTARTED') for e in measured)
            warm_counts = Counter(task_map.get((e['pair_id'], e['method']), {}).get('status', 'UNSTARTED') for e in warm)
            session_row = dict(cell_id=cell_id, study=cell['study'], implementation_id=cell['implementation_id'],
                resource_policy_id=cell['resource_policy_id'], N=cell['N'], ell_bits=cell['ell_bits'], view=cell['view'],
                session_id=session, analytic_status='VALID_WARMUP' if warm_valid else 'WITHHELD_WARMUP_INCOMPLETE_OR_FAILED',
                n_scheduled_measured_pairs=len(pair_ids), n_complete_measured_pairs=complete_pair_count,
                n_incomplete_measured_pairs=len(pair_ids)-complete_pair_count, n_ratio_pairs=len(ratios),
                n_scheduled_warmup_pairs=len(warm)//2, warmup_status_counts=dict(warm_counts), measured_status_counts=dict(counts),
                n_failed_measured_tasks=sum(v for k, v in counts.items() if k not in ('COMPLETE', 'UNSTARTED')),
                n_unstarted_measured_tasks=counts['UNSTARTED'],
                paired_ratio=describe(ratios), packed_TaskTotal_ns=describe(times['packed']), repeated_TaskTotal_ns=describe(times['repeated']),
                method_order_counts_complete_pairs=dict(first_methods),
                uncertainty_interpretation='Descriptive session summary; no session-level CI or significance test.')
            session_rows.append(session_row)
            local_sessions.append(session_row)
            pooled_ratios.extend(ratios)
            for method in pooled_times:
                pooled_times[method].extend(times[method])
        medians = [s['paired_ratio']['median'] for s in local_sessions if s['paired_ratio']['median'] is not None]
        cell_rows.append({**cell, 'n_scheduled_sessions': len(sessions), 'n_sessions_with_ratio': len(medians),
            'n_scheduled_measured_pairs': sum(s['n_scheduled_measured_pairs'] for s in local_sessions),
            'n_complete_measured_pairs': sum(s['n_complete_measured_pairs'] for s in local_sessions),
            'n_incomplete_measured_pairs': sum(s['n_incomplete_measured_pairs'] for s in local_sessions),
            'n_failed_measured_tasks': sum(s['n_failed_measured_tasks'] for s in local_sessions),
            'n_unstarted_measured_tasks': sum(s['n_unstarted_measured_tasks'] for s in local_sessions),
            'paired_ratio': describe(pooled_ratios), 'session_medians': {str(s['session_id']): s['paired_ratio']['median'] for s in local_sessions},
            'observed_session_median_range': [min(medians), max(medians)] if medians else None,
            'packed_TaskTotal_ns': describe(pooled_times['packed']), 'repeated_TaskTotal_ns': describe(pooled_times['repeated']),
            'raw_db_bytes': cell['N'] * ((cell['ell_bits']+7)//8),
            'raw_db_representation': 'per-record byte storage; equals bit-packed size for these byte-aligned performance lengths',
            'native_payload_status': 'ALL_COMPLETE_TASK_COUNTERS_VALIDATED' if any(p['cell_id']==cell_id for p in payload_checks) else 'NO_COMPLETE_TASK',
            'uncertainty_interpretation': SCOPE})
    four = defaultdict(dict)
    for row in session_rows:
        if row['study'] == 'M6':
            key = row['N'], row['ell_bits'], row['view'], row['session_id']
            four[key][row['implementation_id'] + row['resource_policy_id']] = row['paired_ratio']['median']
    treatment_rows = [dict(N=k[0], ell_bits=k[1], view=k[2], session_id=k[3], **{t: v.get(t) for t in ('I1R1','I1R2','I2R1','I2R2')}) for k,v in sorted(four.items())]
    observed_payloads = []
    for cell in cell_rows:
        for method in ('packed','repeated'):
            items = [p for p in payload_checks if p['cell_id']==cell['cell_id'] and p['method']==method]
            for field in ('query_ciphertexts','reply_ciphertexts','query_payload_bytes','reply_payload_bytes'):
                values = {p[field] for p in items}
                require(len(values)<=1, 'Observed payload varies inside same frozen cell')
                observed_payloads.append(dict(cell_id=cell['cell_id'],method=method,metric=field,observed_value=next(iter(values)) if values else None,n_validated_tasks=len(items)))
    return dict(analysis_id=ANALYSIS_ID, data_kind='SYNTHETIC_UNIT_ONLY' if synthetic else 'B3_EMPIRICAL',
        config_sha256=config_sha256, status='COMPLETE' if not failure_rows else 'COMPLETE_WITH_FAILURES' if all(r['status']!='UNSTARTED' for r in failure_rows) else 'PARTIAL',
        inference='DESCRIPTIVE_ONLY', bootstrap=False, p_values=False, historical_pooling=False, scope=SCOPE,
        warmup_policy='Withhold latency summaries for any session/cell with missing or failed scheduled warmup; retain all raw and accounting.',
        scheduled_tasks=len(expected), recorded_tasks=len(tasks), recorded_workers=len(workers),
        complete_tasks=sum(t['status']=='COMPLETE' for t in tasks),
        failed_tasks=sum(t['status']!='COMPLETE' for t in tasks), unstarted_tasks=len(expected)-len(tasks),
        failure_and_unstarted_records=failure_rows, cells=cell_rows, sessions=session_rows,
        measured_complete_pairs=measured_rows, M6_four_treatments_by_session=treatment_rows,
        observed_native_payloads=observed_payloads,
        M6_interpretation='Implementation/resource bundle sensitivity within this frozen new study; not a unique explanation of the historical B1/B2-B difference.',
        M5_interpretation='Fixed encoding J/L/u and observed native counters; no measured competitor or wire traffic inference.')


def latex_number(value):
    return '--' if value is None else f'{value:.3f}'


def ratio_range(cell):
    r = cell['observed_session_median_range']
    return latex_number(cell['paired_ratio']['median']) + (' [' + latex_number(r[0]) + ', ' + latex_number(r[1]) + ']' if r else ' [--]')


def ratio_range_two_lines(cell):
    r=cell['observed_session_median_range']
    lower='['+latex_number(r[0])+', '+latex_number(r[1])+']' if r else '[--]'
    return '\\shortstack{'+latex_number(cell['paired_ratio']['median'])+'\\\\{'+lower+'}}'


def compact_tex(result, study):
    rows = [c for c in result['cells'] if c['study']==study]
    note = ('Entries report median paired ratios [observed session-median range]. '
            'Ranges are descriptive, not confidence intervals; missing values are shown as --. '
            'Incomplete/failed tasks remain in artifact accounting.')
    if study == 'M6':
        header = '\\begingroup\\footnotesize\\setlength{\\tabcolsep}{3pt}\n\\begin{tabular}{rlrrrr}\n\\hline\n$(N,\\ell)$ & View & I1R1 & I1R2 & I2R1 & I2R2 \\\\\n\\hline\n'
        grouped = defaultdict(dict)
        for c in rows:grouped[c['N'],c['ell_bits'],c['view']][c['implementation_id']+c['resource_policy_id']]=c
        body = []
        for key, group in sorted(grouped.items()):
            body.append(' & '.join(['('+str(key[0])+', '+str(key[1])+')',key[2]]+[ratio_range_two_lines(group[t]) if t in group else '--' for t in ('I1R1','I1R2','I2R1','I2R2')])+' \\\\')
    else:
        header = '\\begingroup\\footnotesize\\setlength{\\tabcolsep}{3pt}\n\\begin{tabular}{rrrrll}\n\\hline\n$\\ell$ & $J$ & $L$ & $u$ & View & Ratio [session range] \\\\\n\\hline\n'
        body = [' & '.join([str(c['ell_bits']),str(c['J']),str(c['L']),f"{c['u']:g}",c['view'],ratio_range(c)])+' \\\\' for c in sorted(rows,key=lambda c:(c['ell_bits'],c['view']))]
    prefix = '% SYNTHETIC UNIT FIXTURE: NEVER MANUSCRIPT DATA\n' if result['data_kind']=='SYNTHETIC_UNIT_ONLY' else ''
    return prefix + '% ' + note + '\n' + header + '\n'.join(body) + '\n\\hline\n\\end{tabular}\\endgroup\n\\par\\smallskip{\\footnotesize '+note+'}\\par\n'


def write_results(result, output, provenance):
    output = Path(output).resolve()
    require(output.is_relative_to((ROOT/'artifact/results').resolve()), 'Output must be under artifact/results')
    if output.exists():raise FileExistsError('Never overwrite prior results; choose a new --out')
    output.mkdir(parents=True)
    def write(name,obj):
        with (output/name).open('x',encoding='utf-8',newline='\n') as handle:
            if isinstance(obj,str):handle.write(obj)
            else:json.dump(obj,handle,indent=2,ensure_ascii=False,allow_nan=False)
            handle.write('\n')
    write('B3_summary.json',result)
    write('provenance.json',provenance)
    write('M6_compact.tex',compact_tex(result,'M6'))
    write('M5_compact.tex',compact_tex(result,'M5'))
    flat=[]
    for c in result['cells']:
        flat.append({**{k:c[k] for k in ('cell_id','study','implementation_id','resource_policy_id','N','ell_bits','alpha','view','J','L','u','n_scheduled_measured_pairs','n_complete_measured_pairs','n_incomplete_measured_pairs','n_failed_measured_tasks','n_unstarted_measured_tasks')},
            **{'ratio_'+k:v for k,v in c['paired_ratio'].items()},
            'session_medians':json.dumps(c['session_medians'],sort_keys=True),
            'observed_session_min':c['observed_session_median_range'][0] if c['observed_session_median_range'] else None,
            'observed_session_max':c['observed_session_median_range'][1] if c['observed_session_median_range'] else None,
            **{m+'_TaskTotal_ns_'+k:v for m in ('packed','repeated') for k,v in c[m+'_TaskTotal_ns'].items()}})
    for name,rows in [('B3_cells.csv',flat),('M6_four_treatments_by_session.csv',result['M6_four_treatments_by_session']),('observed_native_payloads.csv',result['observed_native_payloads'])]:
        with (output/name).open('x',encoding='utf-8',newline='') as handle:
            if rows:
                writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    write('output_manifest.json',dict(analysis_id=ANALYSIS_ID,data_kind=result['data_kind'],artifacts=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(output.iterdir()) if p.is_file()]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'artifact/configs/B3_local_protocol.json')
    parser.add_argument('--raw',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    paths=[args.config,args.raw/'task_rows.jsonl',args.raw/'worker_rows.jsonl']
    hashes={str(p):sha(p) for p in paths}
    config=json.loads(args.config.read_text(encoding='utf-8-sig'))
    def read_rows(path):return [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    result=analyze(config,read_rows(paths[1]),read_rows(paths[2]),hashes[str(args.config)])
    provenance=dict(analysis_id=ANALYSIS_ID,python=sys.version,script_sha256=sha(__file__),command_argv=sys.argv,inputs=hashes,
                    bootstrap=False,confidence_intervals=False,synthetic=False)
    require(all(sha(p)==hashes[str(p)] for p in paths),'Input changed during analysis')
    write_results(result,args.out,provenance)
    print(json.dumps({k:result[k] for k in ('status','inference','scheduled_tasks','recorded_tasks','complete_tasks','failed_tasks','unstarted_tasks')}))


if __name__=='__main__':main()
