"""Explicitly synthetic B3 analysis tests; values are never benchmark data."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/analyze_b3.py'
spec=importlib.util.spec_from_file_location('b3_analysis',SCRIPT)
analysis=importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)
HASH='SYNTHETIC_CONFIG_HASH_NOT_AN_EXPERIMENT'


def synthetic_fixture():
    cells=[]
    for impl,policy in [('I1','R1'),('I1','R2'),('I2','R1'),('I2','R2'),('I2','R2')]:
        capacity=len(cells)==4
        alpha=4 if capacity else 2
        ell=65536 if capacity else 512
        J=(ell+7)//8;L=(J+4095)//4096
        cells.append(dict(cell_id=('SYNTHETIC_M5' if capacity else 'SYNTHETIC_M6_'+impl+policy),
            study='M5' if capacity else 'M6',implementation_id=impl,resource_policy_id=policy,
            N=4,ell_bits=ell,alpha=alpha,rho_0=8,w=8*alpha,n=4096,J=J,L=L,u=alpha*J/4096,
            view='COLD',q_id='Q2',ciphertext_bytes=131072))
    config={'synthetic_fixture':True,'cells':cells,'schedule':[]}
    tasks=[];workers=[]
    for cell in cells:
        for session in (1,2,3):
            for phase,count in [('warmup',1),('measured',3)]:
                for repetition in range(count):
                    pair_id=f"{cell['cell_id']}_s{session}_{phase}_{repetition}"
                    order=['packed','repeated'] if repetition%2==0 else ['repeated','packed']
                    entry=dict(cell_id=cell['cell_id'],pair_id=pair_id,session_id=session,phase=phase,method_order=order)
                    config['schedule'].append(entry)
                    stamp=len(tasks)*10000
                    for method in order:
                        duration=(100+repetition*10) if method=='packed' else (101+session*10+repetition*10)
                        start=stamp;end=start+duration;stamp=end+100
                        base={**cell,**entry,'method':method,'experiment_id':'B3','config_sha256':HASH,
                              'timing_label':'SYNTHETIC_UNIT_ONLY','status':'COMPLETE'}
                        worker_count=1 if method=='packed' else cell['alpha']
                        task={**base,'record_type':'task','validation_passed':True,'task_start_ns':start,
                              'task_end_ns':end,'task_total_ns':duration,'failure_reason':'',
                              'query_ciphertexts':worker_count*cell['N'],'reply_ciphertexts':worker_count*cell['L'],
                              'query_payload_bytes':worker_count*cell['N']*131072,'reply_payload_bytes':worker_count*cell['L']*131072}
                        tasks.append(task)
                        for i in range(worker_count):
                            workers.append({**base,'record_type':'worker','worker_index':i,'output_verified':True,
                                'task_start_ns':start+i,'task_end_ns':end,'task_total_ns':duration-i,
                                'query_ciphertexts':cell['N'],'reply_ciphertexts':cell['L'],
                                'query_payload_bytes':cell['N']*131072,'reply_payload_bytes':cell['L']*131072})
    return config,tasks,workers


class B3AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.config,self.tasks,self.workers=synthetic_fixture()

    def run_analysis(self):
        return analysis.analyze(self.config,self.tasks,self.workers,HASH,synthetic=True)

    def test_descriptive_sessions_no_inference(self):
        result=self.run_analysis()
        self.assertEqual(result['status'],'COMPLETE')
        self.assertEqual(result['inference'],'DESCRIPTIVE_ONLY')
        self.assertFalse(result['bootstrap'])
        self.assertFalse(result['p_values'])
        self.assertEqual(len(result['cells']),5)
        self.assertEqual(len(result['sessions']),15)
        cell=result['cells'][0]
        self.assertEqual(cell['paired_ratio']['n'],9)
        self.assertEqual(cell['n_sessions_with_ratio'],3)
        self.assertEqual(cell['observed_session_median_range'],[min(cell['session_medians'].values()),max(cell['session_medians'].values())])
        self.assertEqual(len(result['M6_four_treatments_by_session']),3)
        self.assertIn('not confidence intervals',analysis.compact_tex(result,'M6'))
        self.assertNotIn('\\\\[',analysis.compact_tex(result,'M6'))

    def test_empirical_api_rejects_synthetic(self):
        with self.assertRaises(ValueError):
            analysis.analyze(self.config,self.tasks,self.workers,HASH)

    def test_reject_pilot_and_config_mixture(self):
        self.tasks[0]['timing_label']='B3_PILOT'
        with self.assertRaises(ValueError):self.run_analysis()
        self.tasks[0]['timing_label']='SYNTHETIC_UNIT_ONLY'
        self.tasks[0]['config_sha256']='WRONG'
        with self.assertRaises(ValueError):self.run_analysis()

    def test_reject_duplicate_task(self):
        self.tasks.append(copy.deepcopy(self.tasks[0]))
        with self.assertRaises(ValueError):self.run_analysis()

    def test_measured_failure_remains_accounted(self):
        task=next(t for t in self.tasks if t['phase']=='measured' and t['method']=='repeated')
        task.update(status='TIMEOUT',validation_passed=False,failure_reason='SYNTHETIC injected timeout')
        result=self.run_analysis()
        self.assertEqual(result['status'],'COMPLETE_WITH_FAILURES')
        self.assertEqual(result['failed_tasks'],1)
        self.assertEqual(result['cells'][0]['n_incomplete_measured_pairs'],1)
        self.assertEqual(result['cells'][0]['paired_ratio']['n'],8)
        self.assertEqual(result['cells'][0]['packed_TaskTotal_ns']['n'],9)

    def test_missing_task_not_imputed(self):
        task=next(t for t in self.tasks if t['phase']=='measured' and t['method']=='repeated')
        self.tasks.remove(task)
        self.workers=[w for w in self.workers if (w['pair_id'],w['method'])!=(task['pair_id'],task['method'])]
        result=self.run_analysis()
        self.assertEqual(result['status'],'PARTIAL')
        self.assertEqual(result['unstarted_tasks'],1)
        self.assertEqual(result['cells'][0]['paired_ratio']['n'],8)

    def test_warmup_failure_withholds_affected_session_only(self):
        self.tasks[0].update(status='WRONG_OUTPUT',validation_passed=False,failure_reason='SYNTHETIC failure')
        result=self.run_analysis()
        self.assertEqual(result['cells'][0]['paired_ratio']['n'],6)
        self.assertIsNone(result['cells'][0]['session_medians']['1'])
        self.assertEqual(result['cells'][1]['paired_ratio']['n'],9)
        self.assertTrue(any(not p['included_in_latency_summary'] for p in result['measured_complete_pairs']))

    def test_observed_multiblock_counts(self):
        result=self.run_analysis()
        cell=next(c for c in result['cells'] if c['study']=='M5')
        self.assertEqual((cell['J'],cell['L'],cell['u']),(8192,2,8))
        payload=[p for p in result['observed_native_payloads'] if p['cell_id']==cell['cell_id'] and p['metric']=='reply_ciphertexts']
        self.assertEqual({p['method']:p['observed_value'] for p in payload},{'packed':2,'repeated':8})

    def test_reject_wrong_reply_counter(self):
        self.workers[0]['reply_ciphertexts']=9
        with self.assertRaises(ValueError):self.run_analysis()

    def test_reject_parent_endpoint_or_method_order(self):
        self.tasks[0]['task_total_ns']+=1
        with self.assertRaises(ValueError):self.run_analysis()
        self.tasks[0]['task_total_ns']-=1
        self.config['schedule'][1]['method_order'].reverse()
        with self.assertRaises(ValueError):self.run_analysis()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=Path(__file__).resolve().parents[1]/'results/analysis_unit')
    args=parser.parse_args()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(B3AnalysisTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        cfg,tasks,workers=synthetic_fixture()
        summary=analysis.analyze(cfg,tasks,workers,HASH,synthetic=True)
        analysis.write_results(summary,args.out,dict(data_kind='SYNTHETIC_UNIT_ONLY',not_experimental_evidence=True,
            tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
            script_sha256=analysis.sha(SCRIPT),test_sha256=analysis.sha(__file__),python=sys.version))
    raise SystemExit(0 if result.wasSuccessful() else 1)
