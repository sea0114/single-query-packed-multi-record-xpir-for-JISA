#!/usr/bin/env python3
"""Candidate-specific cost refinement within the original pilot time budget.
SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse
import json
from pathlib import Path
import random
from common import CORE, ROOT, SEEDS, candidates, capacity_workloads, config, main_workloads, now, targets, write_new
from resources import GroupResources, MeasurementLock
from runner import PublicFixture, TaskRunner

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run-id',required=True)
    p.add_argument('--binary',type=Path,required=True)
    a=p.parse_args()
    run=CORE/'runs'/a.run_id
    previous=json.loads((run/'pilot/pilot_001/pilot_report.json').read_text())
    if previous['status']!='COMPLETE':
        raise RuntimeError('Representative pilot must complete before refinement')
    remaining=1800-previous['elapsed_seconds']
    if remaining<=0:
        raise RuntimeError('Original cumulative pilot budget exhausted')
    policy=json.loads((run/'provenance/resource_probe.json').read_text())
    output=run/'pilot/pilot_002'
    output.mkdir(parents=True,exist_ok=False)
    schedule=[]
    rng=random.Random(SEEDS['pilot_targets']+1001)
    for w in main_workloads('compact'):
        cs=candidates(w['alpha'],kind='P')+candidates(w['alpha'],kind='R')
        rng.shuffle(cs)
        schedule.append({'workload':w,'configs':cs})
    for w in capacity_workloads():
        alpha=w['alpha']
        cs=[config('P',w['packed_rho'],1,4),
            config('R',w['packed_rho'],alpha,4//alpha),config('R',24,alpha,4//alpha)]
        rng.shuffle(cs)
        schedule.append({'workload':w,'configs':cs})
    write_new(output/'schedule.json',schedule)
    start=now(); deadline=start+int(remaining*1e9)
    rows=[]; stopped=None; overhead=0
    with MeasurementLock(ROOT,a.run_id+'-pilot-refine'), GroupResources(
            policy['cpu_pool'],run_id=a.run_id+'-pilot-refine',memory_policy=policy['memory_policy'],
            authorize_cgroup_write=policy['memory_policy']=='cgroup') as resources:
        runner=TaskRunner(a.binary,resources,deadline=deadline)
        for index,block in enumerate(schedule):
            w=block['workload']; block_start=now(); block_task_ns=0
            seed=SEEDS['pilot_fixture']+10000+index
            selected=targets(w['N'],w['alpha'],SEEDS['pilot_targets']+10000+index)
            with PublicFixture(w['N'],w['ell_bits'],seed) as fixture:
                for cfg in block['configs']:
                    if now()>=deadline:
                        stopped='CUMULATIVE_PILOT_BUDGET';break
                    labels={'observation_id':f'refine_{index:02}_{cfg["config_id"]}',
                            'phase':'pilot_refinement','workload_id':w['workload_id']}
                    method_start=now()
                    row=runner.run(output/'tasks'/labels['observation_id'],w,cfg,'excluded',fixture,selected,labels=labels)
                    row['budget_full_wall_ns']=now()-method_start
                    rows.append(row);block_task_ns+=row['budget_full_wall_ns']
                    print(json.dumps({'completed':len(rows),'workload_id':w['workload_id'],
                                      'config_id':cfg['config_id'],'status':row['status'],
                                      'wall_s':row['wall_elapsed_ns']/1e9}),flush=True)
                    if row['status']!='COMPLETE':
                        stopped='FUNCTIONAL_OR_RESOURCE_FAILURE';break
            overhead=max(overhead,max(0,now()-block_start-block_task_ns)/1e9)
            if stopped:break
    elapsed=(now()-start)/1e9
    write_new(output/'observations.json',rows)
    lookup={(r['workload_id'],r['config_id']):r for r in rows if r['status']=='COMPLETE'}
    estimates=[]
    for tier in ('compact','minimal'):
        total=0; details=[]; complete=True
        for w in main_workloads(tier):
            cs=candidates(w['alpha'],kind='P')+candidates(w['alpha'],kind='R')
            costs=[]
            for cfg in cs:
                row=lookup.get((w['workload_id'],cfg['config_id']))
                if row is None:complete=False;break
                costs.append((cfg,row['budget_full_wall_ns']/1e9))
            if not complete:break
            base=4*sum(c for cfg,c in costs)
            # Match phase is independent and follows packed layout selection.
            # Bound its complete candidates by the maximum summed policy costs
            # over every possible chosen packed width, without predicting a winner.
            possible_rhos=sorted({cfg['rho_0'] for cfg,c in costs if cfg['kind']=='P'})
            matched=max(4*sum(c for cfg,c in costs if cfg['kind']=='R' and cfg['rho_0']==rho)
                        for rho in possible_rhos)
            base+=matched+overhead*8
            total+=base
            details.append({'workload_id':w['workload_id'],'base_seconds':base,
                            'matched_stage_upper_seconds':matched})
        estimates.append({'tier':tier,'complete_cost_samples':complete,
                          'tuning_base_seconds':total if complete else None,
                          'tuning_with_50pct_margin_seconds':1.5*total if complete else None,
                          'fits_tuning':complete and 1.5*total<=3600,'workloads':details})
    selected=next((e['tier'] for e in estimates if e['fits_tuning']),None) if not stopped else None
    summary={'status':'COMPLETE' if not stopped else 'INCOMPLETE','expected_tasks':sum(len(b['configs']) for b in schedule),
             'completed_tasks':len(rows),'elapsed_seconds':elapsed,
             'cumulative_pilot_seconds':previous['elapsed_seconds']+elapsed,'pilot_budget_seconds':1800,
             'stopped_reason':stopped,'max_block_overhead_seconds':overhead,'tier_tuning_estimates':estimates,
             'provisional_tuning_tier':selected,'formal_tier_not_frozen':True,
             'cost_policy':'Actual complete task wall cost for every candidate and exact fixed capacity config, 50% margin; matched stage bounded over all packed layout choices. Formal cost must be rechecked from actual selected configuration after complete tuning.'}
    write_new(output/'pilot_report.json',summary)
    print(json.dumps(summary),flush=True)
    return 0 if summary['status']=='COMPLETE' and selected else 2

if __name__=='__main__':raise SystemExit(main())
