"""Fail-closed validation for B2-B worker/task records, including synthetic unit fixtures."""
from b2b_common import *
def normalize(x):
    if isinstance(x,dict): return {k:normalize(v) if not k.endswith(('hash','fingerprint','hex')) and k not in ('actual_hex','expected_hex') else v for k,v in x.items()}
    if isinstance(x,list): return [normalize(v) for v in x]
    if isinstance(x,str):
        if x in ('true','false'): return x=='true'
        if x.isdecimal(): return int(x)
    return x
def validate(row):
    assert row['status'] in STATUSES
    assert row['timing_label'] in ('FORMAL',LABEL)
    assert row['stage']=='B2-B' and row['record_type'] in ('task','worker')
    a=row['alpha']; assert a in (2,3,4) and row['rho_0']==8 and row['w']==8*a
    assert row['method'] in ('packed','repeated') and row['view'] in ('COLD','ONLINE')
    if row['timing_label']==LABEL:
        assert row['N']==8 and row['ell_bits']==256
        assert not any(k in row for k in ('task_start_ns','task_end_ns','task_total_ns','phase_ns','cpu_user_ns','cpu_system_ns','aggregate_cpu_ns','start_skew_ns'))
        return True
    assert row['N'] in (1024,4096) and row['ell_bits'] in (512,2048)
    assert row['transport_bytes']=='NOT_MEASURED'
    if row['status']=='COMPLETE':
        assert row['output_verified'] is True
        assert isinstance(row['task_total_ns'],int) and row['task_total_ns']>0
        assert row['task_total_ns']==row['task_end_ns']-row['task_start_ns']
        count=1 if row['record_type']=='worker' or row['method']=='packed' else a
        assert row['query_ciphertexts']==row['N']*count and row['reply_ciphertexts']==count
        assert row['query_payload_bytes']==row['query_ciphertexts']*CT
        assert row['reply_payload_bytes']==row['reply_ciphertexts']*CT
        assert row['cpu_user_ns']>=0 and row['cpu_system_ns']>=0
        assert set(row['phase_ns'])==set(PHASES) and all(v>=0 for v in row['phase_ns'].values())
        if row['record_type']=='worker':
            expected_records=a if row['method']=='packed' else 1
            assert row['coefficient_checks']==4096 and row['segment_checks']==4096*expected_records and row['record_checks']==expected_records
            assert row['all_coefficients_exact'] and row['all_segments_exact'] and row['padding_exact']
            assert row['key_generation_calls']==1 and row['query_encrypt_calls']==row['N']
            assert row['rng_calls']==2+2*row['N'] and row['validation_release_seen']
            assert len(row['cpu_affinity'])==1 and row['omp_max_threads']==1
            events=row['phase_events']; start=row['task_start_ns'];end=row['task_end_ns']
            online={'ConfigureServer','EncodeDB','ImportPreprocess'} if row['view']=='ONLINE' else set()
            for name,event in events.items():
                assert event['end']>=event['begin'] and event['end']-event['begin']==row['phase_ns'][name]
                if name=='ValidationOverhead': assert event['begin']>=end
                elif name in online: assert event['end']<=start
                else: assert start<=event['begin']<=event['end']<=end
        else:
            intervals=row['worker_intervals']; assert len(intervals)==count
            assert row['task_start_ns']==min(x['start_ns'] for x in intervals)
            assert row['task_end_ns']==max(x['end_ns'] for x in intervals)
            assert row['start_skew_ns']==max(x['start_ns'] for x in intervals)-min(x['start_ns'] for x in intervals)
    return True
