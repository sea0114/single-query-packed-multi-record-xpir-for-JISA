"""Frozen pointwise analysis; no native execution and no cross-stage pooling."""
from b2b_common import *
from b2b_schema import validate
import statistics,random
def quantile(values,p):
    if not values: return None
    v=sorted(values); h=(len(v)-1)*p; i=int(h)
    return v[i]+(v[min(i+1,len(v)-1)]-v[i])*(h-i)
def describe(v):
    if not v:return {k:None for k in ('median','Q1','Q3','IQR','min','max','mean','sample_SD')}
    q1=quantile(v,.25);q3=quantile(v,.75)
    return dict(median=statistics.median(v),Q1=q1,Q3=q3,IQR=q3-q1,min=min(v),max=max(v),mean=statistics.mean(v),sample_SD=statistics.stdev(v) if len(v)>1 else None)
def bootstrap(ratios):
    if not ratios:return dict(median=None,CI95=None,n_complete_pairs=0)
    rng=random.Random(BOOTSTRAP_SEED)
    boot=[statistics.median(rng.choices(ratios,k=len(ratios))) for _ in range(10000)]
    return dict(median=statistics.median(ratios),CI95=[quantile(boot,.025),quantile(boot,.975)],n_complete_pairs=len(ratios),resamples=10000,seed=BOOTSTRAP_SEED,sampling='complete pairs with replacement; sample size n_complete; seed reset independently per cell')
def analyze(rows,schedule,freeze_hash,batch_status):
    if not batch_status['environment_valid']:raise ValueError('BATCH_ANALYSIS_INVALID')
    if any(r.get('timing_label')!='FORMAL' or r.get('stage')!='B2-B' or r.get('freeze_manifest_sha256')!=freeze_hash for r in rows):raise ValueError('Reject functional, foreign-stage or foreign-release rows')
    if len({r['batch_id'] for r in rows})!=1:raise ValueError('No pooled batches')
    tasks=[r for r in rows if r['record_type']=='task']; expected={(e['pair_id'],m) for e in schedule for m in e['method_order']}
    if len(tasks)!=624 or {(r['pair_id'],r['method']) for r in tasks}!=expected:raise ValueError('Missing/duplicate/extra scheduled task')
    pairs={}
    for r in tasks:
        validate(r)
        if r['warmup'] and r['status']!='COMPLETE':raise ValueError('BATCH_ANALYSIS_INVALID: warmup failure; no rerun')
        e=next(e for e in schedule if e['pair_id']==r['pair_id'])
        if any(r[k]!=e[k] for k in ('alpha','N','ell_bits','view','warmup','repetition','point_id')):raise ValueError('Schedule metadata mismatch')
        pairs.setdefault(r['pair_id'],{})[r['method']]=r
    out=[]
    for a in (2,3,4):
        for N in (1024,4096):
            for ell in (512,2048):
                for view in ('COLD','ONLINE'):
                    cell=[v for v in pairs.values() if not v['packed']['warmup'] and (v['packed']['alpha'],v['packed']['N'],v['packed']['ell_bits'],v['packed']['view'])==(a,N,ell,view)]
                    assert len(cell)==10
                    complete=[v for v in cell if all(r['status']=='COMPLETE' for r in v.values())]
                    ratios=[v['repeated']['task_total_ns']/v['packed']['task_total_ns'] for v in complete]
                    row=dict(alpha=a,N=N,ell_bits=ell,view=view,paired_completed_task_ratio=bootstrap(ratios),n_complete_pairs=len(complete),n_incomplete_pairs=10-len(complete))
                    for method in ('packed','repeated'):
                        ok=[v[method] for v in cell if v[method]['status']=='COMPLETE']
                        row[method]=dict(TaskTotal_ns=describe([r['task_total_ns'] for r in ok]),aggregate_CPU_ns=describe([r['aggregate_cpu_ns'] for r in ok]),RSS_KiB=describe([r['peak_rss_kib'] for r in ok]),RSS_metric='WORKER_LIFETIME_PEAK_RSS' if method=='packed' else 'SUM_OF_WORKER_PEAK_RSS_UPPER',n_complete=len(ok),n_failed=10-len(ok),aggregate_phase_work_ns={p:describe([r['phase_ns'][p] for r in ok]) for p in PHASES},actual_query_payload_bytes=describe([r['query_payload_bytes'] for r in ok]),actual_reply_payload_bytes=describe([r['reply_payload_bytes'] for r in ok]))
                    pc=row['packed']['aggregate_CPU_ns']['median']; rc=row['repeated']['aggregate_CPU_ns']['median']
                    row['CPU_work_ratio_descriptive']=rc/pc if pc and rc is not None else None
                    out.append(row)
    return dict(cells=out,pointwise_only=True,outlier_removal=False,imputation=False,grand_ratio=None,security_boundary=BOUNDARY)
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--batch',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    from verify_manifest import verify
    verify(); batch=Path(a.batch); rows=[json.loads(x) for x in (batch/'task_rows.jsonl').read_text().splitlines()]
    if (batch/'environment_invalid_incident.json').exists():raise SystemExit('Whole-batch environment incident; analysis invalid')
    result=analyze(rows,read(NOTES/'B2_B_run_schedule.json'),sha(MANIFEST),read(batch/'batch_status.json'));write(Path(a.out),result)
