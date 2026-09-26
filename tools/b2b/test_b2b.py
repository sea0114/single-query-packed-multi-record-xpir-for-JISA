"""Non-performance tests: schedule, schemas, gates, arithmetic, barriers and statistics."""
from b2b_common import *
from b2b_schedule import generate,validate_schedule
from b2b_analyze import quantile,describe,bootstrap,analyze
from b2b_schema import validate
from b2b_runner import aggregate,release_ready,release_validation,run_task
from verify_manifest import verify_entries
import unittest,tempfile,struct,subprocess,select,ast,copy
class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.points=read(NOTES/'B2_B_workload_matrix.json')['points'];cls.schedule=read(NOTES/'B2_B_run_schedule.json')
    def test_schedule_counts_balance_and_mutation(self):
        self.assertTrue(validate_schedule(self.schedule,self.points))
        altered=copy.deepcopy(self.schedule);altered[0]['method_order'].reverse()
        with self.assertRaises(AssertionError):validate_schedule(altered,self.points)
        self.assertEqual(sum(2 for r in self.schedule),624)
        self.assertEqual(sum(1+r['alpha'] for r in self.schedule if not r['warmup']),960)
        for r in range(10):self.assertEqual(len({x['point_id']+x['view'] for x in self.schedule if not x['warmup'] and x['repetition']==r}),24)
    def test_targets_layouts_and_cross_alpha_fixture(self):
        self.assertEqual(targets(1024,3),[170,512,853]);self.assertEqual(targets(4096,4),[512,1536,2560,3584])
        for N in (1024,4096):
            for ell in (512,2048):
                group=[p for p in self.points if (p['N'],p['ell_bits'])==(N,ell)]
                self.assertEqual(len({p['db_fixture_hash'] for p in group}),1)
                self.assertEqual(len({p['encoded_db_hash'] for p in group}),3)
                self.assertTrue(all(len(set(p['target_tuple']))==p['alpha'] and p['J']==ell//8 and p['L']==1 for p in group))
    def test_paired_endpoint_not_duration_sum(self):
        workers=[dict(task_start_ns=100,task_end_ns=180,cpu_user_ns=30,cpu_system_ns=5,phase_ns={p:1 for p in PHASES},query_ciphertexts=8,reply_ciphertexts=1,query_payload_bytes=8*CT,reply_payload_bytes=CT,peak_rss_kib=10),dict(task_start_ns=120,task_end_ns=240,cpu_user_ns=40,cpu_system_ns=6,phase_ns={p:2 for p in PHASES},query_ciphertexts=8,reply_ciphertexts=1,query_payload_bytes=8*CT,reply_payload_bytes=CT,peak_rss_kib=20)]
        r=aggregate(workers);self.assertEqual(r['task_total_ns'],140);self.assertEqual(r['start_skew_ns'],20);self.assertEqual(r['aggregate_cpu_ns'],81);self.assertEqual(r['peak_rss_kib'],30)
        self.assertNotEqual(r['task_total_ns'],sum(w['task_end_ns']-w['task_start_ns'] for w in workers))
    def test_four_independent_exec_release_and_validation(self):
        # No crypto, no observed endpoint/latency data. A deterministic synthetic release tests pipes and process isolation.
        code='import os,sys,struct; r=int(sys.argv[1]); g=int(sys.argv[2]); os.write(r,b"R"); x=os.read(g,8); assert struct.unpack("<Q",x)[0]==5000100; os.write(r,b"D"); assert os.read(g,1)==b"V"'
        children=[];ready=set();done=set()
        try:
            for i in range(4):
                rr,rw=os.pipe();gr,gw=os.pipe();p=subprocess.Popen([sys.executable,'-B','-c',code,str(rw),str(gr)],pass_fds=(rw,gr),stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                os.close(rw);os.close(gr);children.append(dict(rr=rr,gw=gw,process=p))
            self.assertIsNone(release_ready(children,set(),lambda:100));self.assertFalse(release_validation(children,set()))
            while len(ready)<4:
                fds,_,_=select.select([c['rr'] for c in children if c['rr'] not in ready],[],[],5);self.assertTrue(fds)
                for fd in fds:self.assertEqual(os.read(fd,1),b'R');ready.add(fd)
            self.assertEqual(release_ready(children,ready,lambda:100),5000100)
            while len(done)<4:
                fds,_,_=select.select([c['rr'] for c in children if c['rr'] not in done],[],[],5);self.assertTrue(fds)
                for fd in fds:self.assertEqual(os.read(fd,1),b'D');done.add(fd)
            self.assertTrue(release_validation(children,done));self.assertEqual(len({c['process'].pid for c in children}),4)
            for c in children:self.assertEqual(c['process'].wait(timeout=5),0)
        finally:
            for c in children:
                if c['process'].poll() is None:c['process'].kill();c['process'].wait()
                c['process'].stderr.close();os.close(c['rr']);os.close(c['gw'])
    def test_statistics_type7_and_sample_SD(self):
        self.assertEqual(quantile([0,10,20,30],.25),7.5);self.assertEqual(quantile([0,10,20,30],.75),22.5)
        self.assertEqual(describe([1,2,3])['sample_SD'],1)
    def test_bootstrap_reproducibility_synthetic_only(self):
        a=bootstrap([1,2,3,4,5,6,7,8,9,10]);b=bootstrap([1,2,3,4,5,6,7,8,9,10]);self.assertEqual(a,b);self.assertEqual(a['seed'],2026092501);self.assertEqual(a['resamples'],10000)
        self.assertIsNone(bootstrap([])['CI95']);self.assertEqual(bootstrap([2])['CI95'],[2,2])
    def test_analysis_rejects_functional_and_foreign_stage(self):
        for row in [dict(timing_label=LABEL,stage='B2-B'),dict(timing_label='FORMAL',stage='B1')]:
            with self.assertRaises(ValueError):analyze([row],self.schedule,'fake',{'environment_valid':True})
        with self.assertRaises(ValueError):analyze([],self.schedule,'fake',{'environment_valid':False})
        with self.assertRaises(ValueError):analyze([dict(timing_label='FORMAL',stage='B2-B',freeze_manifest_sha256='fake',batch_id='x',record_type='task',pair_id='x',method='packed')],self.schedule,'fake',{'environment_valid':True})
    def test_failure_schema_and_functional_timing_leak(self):
        row=dict(stage='B2-B',record_type='task',timing_label=LABEL,status='COMPLETE',alpha=3,rho_0=8,w=24,N=8,ell_bits=256,method='packed',view='ONLINE')
        self.assertTrue(validate(row))
        with self.assertRaises(AssertionError):validate(dict(row,task_total_ns=1))
        for status in STATUSES[1:]:self.assertTrue(validate(dict(row,timing_label='FORMAL',status=status,N=1024,ell_bits=512,transport_bytes='NOT_MEASURED')))
        with self.assertRaises(AssertionError):validate(dict(row,w=16))
    def test_full_synthetic_batch_incomplete_and_warmup_failure(self):
        # Hand-authored endpoint values only; no actual worker or clock is used and no numerical output is persisted.
        rows=[]
        for e in self.schedule:
            for method in e['method_order']:
                count=1 if method=='packed' else e['alpha'];t=100 if method=='packed' else 200
                rows.append(dict(e,stage='B2-B',record_type='task',method=method,batch_id='SYNTHETIC_UNIT_FIXTURE',timing_label='FORMAL',freeze_manifest_sha256='synthetic',rho_0=8,w=8*e['alpha'],status='COMPLETE',output_verified=True,transport_bytes='NOT_MEASURED',task_start_ns=100,task_end_ns=100+t,task_total_ns=t,start_skew_ns=0,worker_intervals=[dict(start_ns=100,end_ns=100+t)]*count,cpu_user_ns=count*30,cpu_system_ns=count*5,aggregate_cpu_ns=count*35,phase_ns={p:1 for p in PHASES},peak_rss_kib=count*10,query_ciphertexts=e['N']*count,reply_ciphertexts=count,query_payload_bytes=e['N']*count*CT,reply_payload_bytes=count*CT))
        failed=next(r for r in rows if not r['warmup']);failed['status']='TIMEOUT';failed['output_verified']=False
        result=analyze(rows,self.schedule,'synthetic',{'environment_valid':True})
        self.assertEqual(len(result['cells']),24)
        self.assertEqual(sum(c['n_incomplete_pairs'] for c in result['cells']),1)
        self.assertEqual(sum(c['n_complete_pairs'] for c in result['cells']),239)
        next(r for r in rows if r['warmup'])['status']='WRONG_OUTPUT'
        with self.assertRaises(ValueError):analyze(rows,self.schedule,'synthetic',{'environment_valid':True})
        with self.assertRaises(ValueError):analyze(rows+[rows[-1]],self.schedule,'synthetic',{'environment_valid':True})
    def test_resource_caps_and_payload(self):
        model=read(NOTES/'B2_B_resource_preflight.json');self.assertEqual(model['status'],'FEASIBLE')
        self.assertTrue(all(p['aggregate_cap_feasible'] and p['per_worker_cap_feasible'] for p in model['model']))
        for p in model['model']:
            self.assertEqual(p['repeated_query_bytes'],p['alpha']*p['packed_query_bytes']);self.assertEqual(p['repeated_reply_bytes'],p['alpha']*CT)
        self.assertEqual(CAPS['per_worker_address_space_bytes'],8*2**30)
    def test_manifest_missing_tampered_size_extra_role(self):
        with tempfile.TemporaryDirectory(prefix='b2b-test-') as d:
            p=Path(d)/'a';p.write_text('abc');entry=dict(path='a',size=3,sha256=sha(p),role='TOOL');m={'artifacts':[entry]}
            self.assertFalse(verify_entries(m,d)[0]);p.write_text('xyz');self.assertTrue(verify_entries(m,d)[0]);p.unlink();self.assertTrue(verify_entries(m,d)[0])
    def test_formal_execution_guard(self):
        with self.assertRaises(ValueError):run_task({},point(2,8,256),dict(method='packed'),LOG/'SHOULD_NOT_EXIST',functional=False)
        with self.assertRaises(ValueError):run_task({},self.points[0],dict(method='packed'),LOG/'SHOULD_NOT_EXIST',functional=True)
        self.assertFalse((LOG/'SHOULD_NOT_EXIST').exists())
    def test_source_and_all_python_parse(self):
        for p in HERE.glob('*.py'):ast.parse(p.read_text(),filename=str(p))
        source=(HERE/'b2b_worker.cpp').read_text()
        self.assertIn('m1::encrypt_integer(*client,messages[i])',source);self.assertIn('w==a*rho',source)
        self.assertNotIn('encrypt(1)',source);self.assertNotIn('MULTI_THREAD',read(LOG/'build_manifest.json')['compile_flags'])
        self.assertTrue(all(sha(ROOT/n)==h for n,h in read(LOG/'build_manifest.json')['source_hashes'].items()))
if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ContractTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if '--seal-results' in sys.argv:
        name=sys.argv[sys.argv.index('--out')+1] if '--out' in sys.argv else 'contract_tests.json'
        write(LOG/name,dict(status='PASS' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),synthetic_only=True,native_crypto_executions=0,performance_observations=0,bootstrap_results_persisted=False))
    raise SystemExit(0 if result.wasSuccessful() else 1)
