#!/usr/bin/env python3
"""Absolute-cost pilot and pre-formal tier feasibility, never speedup selection.

SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse
import datetime
import json
from pathlib import Path
import random
from common import CORE, ROOT, SEEDS, candidates, capacity_workloads, config, main_workloads, now, targets, write_new
from resources import GroupResources, MeasurementLock
from runner import PublicFixture, TaskRunner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--pilot-id', default='pilot_001')
    args = parser.parse_args()
    run = CORE / 'runs' / args.run_id
    report = json.loads((run / 'provenance/resource_probe.json').read_text())
    if report['status'] != 'COMPLETE':
        raise RuntimeError('resource preflight incomplete')
    functional = json.loads((run / 'functional/functional_001/functional_report.json').read_text())
    if functional['status'] != 'PASS_FINITE_NATIVE_FUNCTIONAL_GATE':
        raise RuntimeError('functional gate incomplete')
    output = run / 'pilot' / args.pilot_id
    output.mkdir(parents=True, exist_ok=False)
    profiles = [
        {'N':256,'alpha':2,'ell_bits':4096},
        {'N':256,'alpha':4,'ell_bits':32768},
        {'N':4096,'alpha':2,'ell_bits':4096},
        {'N':4096,'alpha':4,'ell_bits':32768},
        {'N':1024,'alpha':3,'ell_bits':32768},
        {'N':1024,'alpha':4,'ell_bits':4096},
        {'N':1024,'alpha':2,'ell_bits':98304},
        {'N':1024,'alpha':4,'ell_bits':49152},
    ]
    # Each profile probes the narrowest/widest layouts and serial/parallel
    # policies. The report deliberately uses upper costs, not winner effects.
    schedule = []
    rng = random.Random(SEEDS['pilot_targets'] + 17)
    for index, profile in enumerate(profiles):
        alpha = profile['alpha']
        configs = [config('P',4,1,1), config('P',24//alpha,1,4),
                   config('R',4,1,1),config('R',24,1,1),
                   config('R',4,alpha,4//alpha),config('R',24,alpha,4//alpha)]
        for scope in ('included','excluded'):
            for round_id in range(3):
                order = list(configs)
                rng.shuffle(order)
                schedule.append({'profile_id':index,'workload':profile,'scope':scope,
                                 'round_id':round_id,'phase':'warmup' if round_id==0 else 'pilot',
                                 'fixture_seed':SEEDS['pilot_fixture']+index*10+round_id,
                                 'target_seed':SEEDS['pilot_targets']+index*10+round_id,
                                 'configs':order})
    write_new(output/'schedule.json',schedule)
    start = now()
    deadline = start + 1800_000_000_000
    rows = []
    stopped = None
    with MeasurementLock(ROOT,args.run_id+'-pilot'):
        with GroupResources(report['cpu_pool'],run_id=args.run_id+'-pilot',
                            memory_policy=report['memory_policy'],
                            authorize_cgroup_write=report['memory_policy']=='cgroup') as resources:
            runner = TaskRunner(args.binary,resources,deadline=deadline)
            for block_index, block in enumerate(schedule):
                if now() >= deadline:
                    stopped = 'PILOT_BUDGET'
                    break
                w = block['workload']
                block_start = now()
                selected = targets(w['N'],w['alpha'],block['target_seed'])
                with PublicFixture(w['N'],w['ell_bits'],block['fixture_seed']) as fixture:
                    for cfg in block['configs']:
                        labels = {'observation_id':f'pilot_{block_index:03}_{cfg["config_id"]}',
                                  'phase':block['phase'],'profile_id':block['profile_id'],
                                  'block_id':block_index,'round_id':block['round_id']}
                        row = runner.run(output/'tasks'/labels['observation_id'],w,cfg,
                                         block['scope'],fixture,selected,labels=labels)
                        rows.append(row)
                        print(json.dumps({'completed':len(rows),'profile_id':block['profile_id'],
                                          'config_id':cfg['config_id'],'scope':block['scope'],
                                          'status':row['status'],'wall_s':row['wall_elapsed_ns']/1e9}),flush=True)
                        if row['status']!='COMPLETE':
                            stopped = 'FUNCTIONAL_OR_RESOURCE_FAILURE'
                            break
                write_new(output/'blocks'/f'{block_index:03}.json',
                          {'block_wall_ns':now()-block_start,'fixture_and_target_seed':
                           [block['fixture_seed'],block['target_seed']]})
                if stopped:
                    break
    elapsed = (now()-start)/1e9
    write_new(output/'observations.json',rows)
    maxima = {}
    for row in rows:
        if row['status']=='COMPLETE':
            key=str(row['workload']['N'])
            maxima[key]=max(maxima.get(key,0),row['wall_elapsed_ns']/1e9)
    # Include observed fixture/dispatch/logging/block overhead in addition to
    # each complete task. One second between sessions is part of all estimates.
    overhead_per_block = 0
    for path in (output/'blocks').glob('*.json'):
        index=int(path.stem)
        block_cost=json.loads(path.read_text())['block_wall_ns']/1e9
        cost=sum(row['wall_elapsed_ns']/1e9 for row in rows if row['block_id']==index)
        overhead_per_block=max(overhead_per_block,max(0,block_cost-cost))
    estimates=[]
    for tier in ('full','compact','minimal'):
        workloads=main_workloads(tier)
        feasible_keys=all(str(w['N']) in maxima for w in workloads+capacity_workloads())
        if not feasible_keys:
            estimates.append({'tier':tier,'fits':False,'reason':'Pilot profiles incomplete'})
            continue
        formal_base=sum(2*10*7*(3*maxima[str(w['N'])]+overhead_per_block)
                        for w in workloads+capacity_workloads()) + 9
        tuning_base=0
        candidate_counts={}
        for w in workloads:
            alpha=w['alpha']
            count=len(candidates(alpha,kind='P'))+len(candidates(alpha,kind='R'))+max(
                len(candidates(alpha,kind='R',rho=r)) for r in (4,6,8,12) if r*alpha<=24)
            candidate_counts[w['workload_id']]=count
            tuning_base += 4*count*(maxima[str(w['N'])]+overhead_per_block)
        formal_with_margin=1.5*formal_base
        tuning_with_margin=1.5*tuning_base
        estimates.append({'tier':tier,'conditions':2*(len(workloads)+8),
                          'formal_base_seconds':formal_base,'formal_with_50pct_margin_seconds':formal_with_margin,
                          'tuning_base_seconds':tuning_base,'tuning_with_50pct_margin_seconds':tuning_with_margin,
                          'candidate_counts':candidate_counts,
                          'fits':feasible_keys and formal_with_margin<=16200 and tuning_with_margin<=3600})
    chosen=next((e['tier'] for e in estimates if e['fits']),None) if not stopped and len(rows)==288 else None
    summary={'status':'COMPLETE' if not stopped and len(rows)==288 else 'INCOMPLETE',
             'run_id':args.run_id,'pilot_id':args.pilot_id,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'elapsed_seconds':elapsed,'budget_seconds':1800,'stopped_reason':stopped,
             'completed_tasks':len(rows),'expected_tasks':288,
             'max_task_wall_seconds_by_N':maxima,'max_block_overhead_seconds':overhead_per_block,
             'method':'Conservative maximum observed complete task cost per N, including validation/process/runtime/logging; same-N shorter untested cases bounded by maximum-length profile; 50% margin; assumes no baseline deduplication',
             'tier_estimates':estimates,'selected_tier':chosen,
             'author_decision_required':chosen is None}
    write_new(output/'pilot_report.json',summary)
    print(json.dumps(summary),flush=True)
    return 0 if summary['status']=='COMPLETE' and chosen else 2


if __name__=='__main__':
    raise SystemExit(main())
