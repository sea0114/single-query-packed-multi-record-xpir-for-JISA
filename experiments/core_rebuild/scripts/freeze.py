#!/usr/bin/env python3
"""Freeze verified design, winners, budgets and literal formal schedule.
SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse
import datetime
import itertools
import json
from pathlib import Path
import random
from common import BACKEND_COMMIT, CORE, ROOT, Q, SEEDS, capacity_workloads, config, integer_screen, main_workloads, sha, targets, write_new
from preflight import inventory

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run-id',required=True)
    p.add_argument('--manifest',type=Path,required=True)
    a=p.parse_args();run=CORE/'runs'/a.run_id
    tuning=json.loads((run/'tuning/tuning_001/tuning_report.json').read_text())
    if tuning['status']!='COMPLETE':raise RuntimeError('Tuning incomplete')
    representative=json.loads((run/'pilot/pilot_001/pilot_report.json').read_text())
    refinement=json.loads((run/'pilot/pilot_002/pilot_report.json').read_text())
    policy=json.loads((run/'provenance/resource_probe.json').read_text())
    functional=json.loads((run/'functional/functional_001/functional_report.json').read_text())
    if not (representative['status']=='COMPLETE' and refinement['status']=='COMPLETE'
            and policy['status']=='COMPLETE' and functional['status']=='PASS_FINITE_NATIVE_FUNCTIONAL_GATE'):
        raise RuntimeError('A required pre-formal gate is incomplete')
    if refinement['cumulative_pilot_seconds']>1800 or tuning['elapsed_seconds']>3600:
        raise RuntimeError('Authorized measurement stage budget exceeded')
    build=json.loads(a.manifest.read_text());binary=ROOT/build['binary']
    if sha(binary)!=build['binary_sha256']:raise RuntimeError('Binary changed')
    if functional['native_binary_sha256']!=build['binary_sha256']:
        raise RuntimeError('Functional gate used a different binary')
    for name,digest in build['source_hashes'].items():
        if sha(ROOT/name)!=digest:raise RuntimeError('Compiled source changed')
    winners={w['workload']['workload_id']:w for w in tuning['winners']}
    if len(winners)!=len(tuning['winners']) or set(winners)!={w['workload_id'] for w in main_workloads(tuning['provisional_tier'])}:
        raise RuntimeError('Tuning workload set is incomplete or duplicated')
    tuning_rows=json.loads((run/'tuning/tuning_001/observations.json').read_text())
    if any(r['status']!='COMPLETE' or not r['validated'] for r in tuning_rows):
        raise RuntimeError('Tuning contains failed observations')
    for item in winners.values():
        if set(item['roles'])!={'P','R_matched','R_independent'}:
            raise RuntimeError('Winner roles incomplete')
        if item['baseline_alias']!=(item['roles']['R_matched']==item['roles']['R_independent']):
            raise RuntimeError('Alias metadata inconsistent')
    capacity=[]
    pilot_rows=json.loads((run/'pilot/pilot_002/observations.json').read_text())
    if len(pilot_rows)!=refinement['expected_tasks'] or any(r['status']!='COMPLETE' or not r['validated'] for r in pilot_rows):
        raise RuntimeError('Candidate cost pilot is incomplete')
    for w in capacity_workloads():
        alpha=w['alpha'];roles={'P':config('P',w['packed_rho'],1,4),
                               'R_matched':config('R',w['packed_rho'],alpha,4//alpha),
                               'R_independent':config('R',24,alpha,4//alpha)}
        bounds={role:max(r['budget_full_wall_ns'] for r in pilot_rows
                         if r['workload_id']==w['workload_id'] and r['config_id']==cfg['config_id'])
                for role,cfg in roles.items()}
        capacity.append({'workload':w,'roles':roles,'full_wall_upper_ns':bounds,'baseline_alias':False})
    assessments=[];chosen=None;chosen_specs=None
    tiers=('full','compact','minimal')
    for tier in tiers[tiers.index(tuning['provisional_tier']):]:
        if tier in [e['tier'] for e in assessments]:continue
        workload_ids=[w['workload_id'] for w in main_workloads(tier)]
        if not all(i in winners for i in workload_ids):continue
        specs=[winners[i] for i in workload_ids]+capacity
        base=9.0
        for item in specs:
            # Alias roles refer to the same physical task, never independent samples.
            physical={cfg['config_id']:role for role,cfg in item['roles'].items()}
            cost=sum(item['full_wall_upper_ns'][role]/1e9 for role in physical.values())
            base+=2*10*7*(cost+refinement['max_block_overhead_seconds'])
        entry={'tier':tier,'base_seconds':base,'with_50pct_margin_seconds':1.5*base,
               'fits':1.5*base<=16200,'conditions':2*len(specs)}
        assessments.append(entry)
        if entry['fits'] and chosen is None:chosen=tier;chosen_specs=specs
    if chosen is None:
        report={'status':'AUTHOR_DECISION_REQUIRED','formal_budget_seconds':16200,
                'cost_assessments':assessments,'reason':'Even the minimum permitted tier does not fit with 50% margin',
                'formal_started':False,'manuscript_rewritten':False}
        write_new(run/'provenance/budget_decision.json',report)
        print(json.dumps(report));return 2
    conditions=[]
    for item in chosen_specs:
        w=item['workload'];roles=item['roles']
        for scope in ('included','excluded'):
            cid=w['workload_id']+'_'+scope
            conditions.append({'condition_id':cid,'workload':w,'scope':scope,
                               'roles':{role:cfg['config_id'] for role,cfg in roles.items()},
                               'configurations':{cfg['config_id']:cfg for cfg in roles.values()},
                               'baseline_alias':item['baseline_alias'],
                               'arithmetic_screens':{role:integer_screen(w['N'],w['ell_bits'],
                                   w['alpha'] if role=='P' else 1,cfg['rho_0']) for role,cfg in roles.items()}})
    if any(not screen['strict_no_wrap'] for c in conditions for screen in c['arithmetic_screens'].values()):
        raise RuntimeError('A frozen role fails the integer no-wrap screen')
    schedule=[];expected=[];seeds=[]
    condition_rng=random.Random(SEEDS['formal_schedule'])
    order_rng=random.Random(SEEDS['formal_schedule']+1_000_000)
    for session in range(1,11):
        ordered=list(range(len(conditions)));condition_rng.shuffle(ordered)
        for condition_index in ordered:
            condition=conditions[condition_index]
            ids=sorted(condition['configurations'])
            permutations=list(itertools.permutations(ids))
            if len(ids)==2:permutations*=3
            assert len(permutations)==6
            order_rng.shuffle(permutations)
            warmup=list(ids);order_rng.shuffle(warmup)
            for block in range(7):
                fixture_seed=SEEDS['formal_fixture']+1_000_000+session*10000+condition_index*100+block
                target_seed=SEEDS['formal_targets']+1_000_000+session*10000+condition_index*100+block
                seeds.append(fixture_seed)
                label={'condition_id':condition['condition_id'],'session_id':session,
                       'block_id':block,'phase':'warmup' if block==0 else 'measured',
                       'fixture_seed':fixture_seed,'target_seed':target_seed,
                       'targets':targets(condition['workload']['N'],condition['workload']['alpha'],target_seed),
                       'order':warmup if block==0 else list(permutations[block-1])}
                schedule.append(label)
                for cid in label['order']:
                    expected.append({k:label[k] for k in ('condition_id','session_id','block_id','phase')}|{'config_id':cid})
    assert len(seeds)==len(set(seeds))
    output=run/'provenance/freeze.json'
    source_files=list((CORE/'scripts').glob('*.py'))+list((CORE/'src').glob('*'))+list((CORE/'tests').glob('*.*'))
    source_hashes={str(path.relative_to(ROOT)):sha(path) for path in source_files if path.is_file()}
    result={'schema':'CORE_FREEZE_V1','status':'FROZEN_NOT_FORMALLY_MEASURED','run_id':a.run_id,
            'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'tier':chosen,
            'backend_commit':BACKEND_COMMIT,'n':4096,'q':str(Q),'w':24,'t':2**24,
            'native_error_bound':398,'native_error_path':'Berr200: masked bits followed by one subtraction; support 0..398; not a certified sampling law or security level',
            'recursion_dimension':1,'database_aggregation':1,'build_manifest':str(a.manifest.relative_to(ROOT)),
            'build_manifest_sha256':sha(a.manifest),
            'gate_report_hashes':{str(path.relative_to(ROOT)):sha(path) for path in
                (run/'pilot/pilot_001/pilot_report.json',run/'pilot/pilot_002/pilot_report.json',
                 run/'tuning/tuning_001/tuning_report.json',run/'provenance/resource_probe.json',
                 run/'functional/functional_001/functional_report.json',run/'functional/source_gate.json',
                 run/'functional/runner_source_review.json',run/'provenance/citation_verification.json')},
            'binary':build['binary'],'binary_sha256':build['binary_sha256'],'source_hashes':source_hashes,
            'resource_policy':policy['memory_policy'],'cpu_pool':policy['cpu_pool'],'memory_threshold_bytes':8*2**30,
            'environment_at_freeze':inventory(),
            'hard_memory_limit':policy['hard_limit_verified'],'monitor_interval_seconds':1.0,
            'competition_scan_interval_seconds':2.0,'host_isolation':'WSL guest affinity only; Windows host not exclusive',
            'seeds':SEEDS,'condition_order_seed':SEEDS['formal_schedule'],
            'method_order_seed':SEEDS['formal_schedule']+1_000_000,'formal_fixture_namespace_offset':1_000_000,
            'timing':{'clock':'CLOCK_MONOTONIC_RAW','included':'Coordinator before prepare GO/encode/import/shared construction through all full records and DONE received',
                      'excluded':'Sealed shared data prepared before query GO through all full records and DONE received',
                      'both_include':'Fresh KeyGen, query, reply, extraction, dispatch and record collection',
                      'outside':'Fresh-exec runtime/public fixture load before READY; validation/hash/JSON/log disk writes only after V',
                      'cpu':'Coordinator SELF plus native G-to-D rusage; included additionally counts single owner; exited children retained'},
            'failure_policy':'Retain failures/OOM/timeout/wrong output/not started. Any failed method invalidates its block; any incomplete/warmup-failed condition excluded from performance evidence; no successful-subset analysis or cross-version repair',
            'budgets_seconds':{'pilot':1800,'tuning':3600,'formal':16200},
            'actual_pilot_seconds':refinement['cumulative_pilot_seconds'],'actual_tuning_seconds':tuning['elapsed_seconds'],
            'formal_cost_assessments':assessments,'cost_estimate_note':'Empirical conservative maximum complete-wall costs of actual winning configs and exact fixed capacity configs, plus fixture/block overhead, 50% margin; not a runtime guarantee',
            'sessions':10,'warmup_blocks':1,'measured_blocks_per_session':6,'session_interval_seconds':1,
            'statistics':{'ratio':'baseline/P per paired block; session median of six ratios; median of ten session medians',
                          'absolute':'session median then median across ten sessions',
                          'bootstrap_resamples':10000,'unit':'whole session, common index vectors across both contrasts and all metrics',
                          'interval':'pointwise 95% percentile, linear interpolation at (B-1)*p; approximate resampling summary, no coverage or cross-host guarantee'},
            'conditions':conditions,'schedule':schedule,'expected_observations':expected,
            'figure_condition_map':{'retrieval_performance':[c['condition_id'] for c in conditions if c['workload']['study']=='primary'],
                                    'capacity_tradeoff':[c['condition_id'] for c in conditions if c['workload']['study']=='capacity'],
                                    'costs':[c['condition_id'] for c in conditions]}}
    write_new(output,result)
    print(json.dumps({'status':result['status'],'tier':chosen,'conditions':len(conditions),
                      'physical_tasks':len(expected),'cost_assessments':assessments,'freeze':str(output)}))
    return 0

if __name__=='__main__':raise SystemExit(main())
