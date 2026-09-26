"""Exactly three tiny packed checks. No endpoint, phase, CPU or RSS observations retained."""
from b2b_common import *
from b2b_runner import run_task
def main():
    if (LOG/'smoke_started.json').exists():raise RuntimeError('Smoke already attempted; no rerun/replacement')
    config=read(LOG/'freeze_config.json')
    write(LOG/'smoke_started.json',dict(planned_alpha=[2,3,4],N=8,ell_bits=256,new_native_processes=3,label=LABEL,reason='New generalized performance extraction and both staging views require minimal correctness validation; concurrency tested with non-cryptographic unit fixtures.'))
    results=[];fingerprints=[]
    for a,view in ((2,'COLD'),(3,'ONLINE'),(4,'COLD')):
        p=point(a,8,256);entry=dict(run_id=f'smoke_A{a}',pair_id=f'functional_A{a}',method='packed',view=view,warmup=False,repetition=0,batch_id='B2_B_FREEZE_FUNCTIONAL')
        parent,workers=run_task(config,p,entry,LOG/f'smoke_A{a}',functional=True)
        assert parent['status']=='COMPLETE' and len(workers)==1
        row=workers[0];raw=fixture(8,256);fields=row['packed_coefficients']
        expected=[sum((raw[t][j] if j<32 else 0)*(1<<(8*r)) for r,t in enumerate(p['target_tuple'])) for j in range(4096)]
        assert fields==expected and row['actual_hex']==[raw[t].hex() for t in p['target_tuple']]
        assert not any(k.endswith('_ns') for k in row)
        fingerprints.append(row['key_fingerprint']);results.append(dict(alpha=a,N=8,ell_bits=256,view=view,status='PASS',packed_coefficients_independently_checked=4096,records_independently_checked=a,timing_label=LABEL,timing_collected=False))
    assert len(set(fingerprints))==3
    write(LOG/'smoke_validation.json',dict(status='PASS',new_native_processes=3,formal_observations=0,TaskTotal_fields=0,cases=results))
    print(json.dumps(dict(smoke='PASS',cases=3,formal_observations=0,TaskTotal_fields=0)))
if __name__=='__main__':main()
