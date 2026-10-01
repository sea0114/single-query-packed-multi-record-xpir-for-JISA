#!/usr/bin/env python3
"""Complete interleaved candidate tuning, independently from formal samples.
SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse
import json
from pathlib import Path
import random
import statistics
from common import CORE, ROOT, SEEDS, candidates, main_workloads, now, sha, targets, write_new
from resources import GroupResources, MeasurementLock
from runner import PublicFixture, TaskRunner

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run-id',required=True)
    p.add_argument('--binary',type=Path,required=True)
    a=p.parse_args();run=CORE/'runs'/a.run_id
    pilot=json.loads((run/'pilot/pilot_002/pilot_report.json').read_text())
    if pilot['status']!='COMPLETE' or not pilot['provisional_tuning_tier']:
        raise RuntimeError('Complete feasible candidate-cost pilot required')
    tier=pilot['provisional_tuning_tier'];workloads=main_workloads(tier)
    policy=json.loads((run/'provenance/resource_probe.json').read_text())
    output=run/'tuning/tuning_001';output.mkdir(parents=True,exist_ok=False)
    start=now();deadline=start+3600_000_000_000
    rows=[];winners=[];schedules=[];stopped=None
    with MeasurementLock(ROOT,a.run_id+'-tuning'),GroupResources(
            policy['cpu_pool'],run_id=a.run_id+'-tuning',memory_policy=policy['memory_policy'],
            authorize_cgroup_write=policy['memory_policy']=='cgroup') as resources:
        runner=TaskRunner(a.binary,resources,deadline=deadline)
        for index,w in enumerate(workloads):
            stage_winners={}
            for stage in ('packed_and_independent','matched'):
                if stage=='packed_and_independent':
                    cs=candidates(w['alpha'],kind='P')+candidates(w['alpha'],kind='R')
                else:
                    cs=candidates(w['alpha'],kind='R',rho=stage_winners['P']['rho_0'])
                stage_seed=SEEDS['tuning_schedule']+index*100+(0 if stage=='packed_and_independent' else 50)
                rng=random.Random(stage_seed)
                orders=[]
                for round_id in range(4):
                    order=list(cs);rng.shuffle(order);orders.append(order)
                schedule={'workload':w,'stage':stage,'schedule_seed':stage_seed,
                          'candidate_table':cs,'round_orders':orders,'warmup_round':0,'measured_rounds':[1,2,3]}
                write_new(output/'schedules'/f'{index:02}_{stage}.json',schedule);schedules.append(schedule)
                stage_rows=[]
                for round_id,order in enumerate(orders):
                    seed=SEEDS['tuning_fixture']+index*100+round_id+(0 if stage=='packed_and_independent' else 50)
                    target_seed=SEEDS['tuning_targets']+index*100+round_id+(0 if stage=='packed_and_independent' else 50)
                    selected=targets(w['N'],w['alpha'],target_seed)
                    with PublicFixture(w['N'],w['ell_bits'],seed) as fixture:
                        for cfg in order:
                            if now()>=deadline:stopped='TUNING_BUDGET';break
                            labels={'observation_id':f'tune_{index:02}_{stage}_{round_id}_{cfg["config_id"]}',
                                    'phase':'warmup' if round_id==0 else 'tuning','workload_id':w['workload_id'],
                                    'stage':stage,'round_id':round_id}
                            method_start=now()
                            row=runner.run(output/'tasks'/labels['observation_id'],w,cfg,'excluded',fixture,selected,labels=labels)
                            row['budget_full_wall_ns']=now()-method_start
                            rows.append(row);stage_rows.append(row)
                            print(json.dumps({'completed':len(rows),'workload_id':w['workload_id'],
                                              'stage':stage,'round_id':round_id,'config_id':cfg['config_id'],
                                              'status':row['status']}),flush=True)
                            if row['status']!='COMPLETE':stopped='CANDIDATE_FAILURE';break
                    if stopped:break
                if stopped:break
                roles=('P','R_independent') if stage=='packed_and_independent' else ('R_matched',)
                rankings={}
                for role in roles:
                    kind='P' if role=='P' else 'R'
                    candidate_results=[]
                    for cfg in cs:
                        if cfg['kind']!=kind:continue
                        measured=[r for r in stage_rows if r['phase']=='tuning' and r['config_id']==cfg['config_id']]
                        assert len(measured)==3 and all(r['status']=='COMPLETE' for r in measured)
                        candidate_results.append({'configuration':cfg,'median_task_latency_ns':statistics.median(
                            r['task_latency_ns'] for r in measured),'max_full_wall_ns':max(
                            r['budget_full_wall_ns'] for r in stage_rows if r['config_id']==cfg['config_id'])})
                    candidate_results.sort(key=lambda r:(r['median_task_latency_ns'],r['configuration']['config_id']))
                    rankings[role]=candidate_results;stage_winners[role]=candidate_results[0]['configuration']
                write_new(output/'rankings'/f'{index:02}_{stage}.json',rankings)
            if stopped:break
            chosen={'workload':w,'roles':stage_winners,
                    'full_wall_upper_ns':{role:max(r['budget_full_wall_ns'] for r in rows
                         if r['workload_id']==w['workload_id'] and r['config_id']==cfg['config_id'])
                         for role,cfg in stage_winners.items()},
                    'baseline_alias':stage_winners['R_matched']==stage_winners['R_independent']}
            winners.append(chosen);write_new(output/'winners'/f'{index:02}.json',chosen)
    report={'status':'COMPLETE' if not stopped and len(winners)==len(workloads) else 'INCOMPLETE',
            'provisional_tier':tier,'completed_workloads':len(winners),'planned_workloads':len(workloads),
            'completed_tasks':len(rows),'elapsed_seconds':(now()-start)/1e9,'budget_seconds':3600,
            'stopped_reason':stopped,'winners':winners,
            'source_hashes':{name:sha(Path(__file__).with_name(name)) for name in
                             ('tune.py','runner.py','common.py','resources.py')},
            'objective':'Median of three complete task latencies in preprocessing-excluded scope; one separate warmup; stable lexical config ID tie break; no formal selection'}
    write_new(output/'observations.json',rows);write_new(output/'tuning_report.json',report)
    print(json.dumps({'status':report['status'],'completed_workloads':len(winners),
                      'elapsed_seconds':report['elapsed_seconds']}),flush=True)
    return 0 if report['status']=='COMPLETE' else 2

if __name__=='__main__':raise SystemExit(main())
