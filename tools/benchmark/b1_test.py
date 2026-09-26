"""Non-native tests; no synthetic row is written to the formal result directory."""
import unittest,copy
from b1_common import *
from b1_report import build_results
from analysis import analyze,paired_ratio

class B1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.m,cls.entries,cls.points=entries_and_manifest()
    def test_schedule_domain_and_counts(self):
        self.assertEqual(len(self.entries),4896)
        self.assertEqual(sum(1 if e['method']=='packed' else 2 for e in self.entries),7344)
        self.assertEqual(sum(e['warmup'] for e in self.entries),576)
    def test_unstarted_all_statuses_both_methods(self):
        for original in self.entries[:2]:
            e={**original,'batch_id':BATCH_ID};p=self.points[e['point_id']]
            for status in ('RESOURCE_LIMIT','RUNTIME_FAIL','TIMEOUT','WRONG_OUTPUT'):
                parent,workers=unavailable(self.m,p,e,status,'synthetic unstarted test')
                annotate(parent,workers,e,'TEST_ONLY')
                for row in workers+[parent]:
                    validate_row(row)
                    self.assertIsNone(row['task_total_ns']);self.assertFalse(row['execution_attempted'])
                    self.assertIsNone(row['query_payload_bytes'])
    def test_contamination_rejection(self):
        e={**self.entries[0],'batch_id':BATCH_ID};p=self.points[e['point_id']]
        parent,workers=unavailable(self.m,p,e,'RUNTIME_FAIL','test');annotate(parent,workers,e,'TEST_ONLY')
        for key,value in [('timing_label','DRY_RUN / NOT_FOR_ANALYSIS'),('analysis_scope','T0_REPEATED_ONLY'),('batch_id','other')]:
            r=copy.deepcopy(parent);r[key]=value
            with self.assertRaises(AssertionError):validate_row(r)
    def test_frozen_bootstrap_pair_values(self):
        r=paired_ratio([(100,200),(200,500)])
        self.assertEqual(r['median_paired_ratio'],2.25);self.assertEqual(r['CI95'],[2.0,2.5])
        self.assertEqual(r['resamples'],10000);self.assertEqual(r['seed'],2026092401)
    def test_invalid_batch_suppresses_all_statistics(self):
        tasks=[]
        for original in self.entries:
            e={**original,'batch_id':BATCH_ID};parent,_=unavailable(self.m,self.points[e['point_id']],e,'RUNTIME_FAIL','NOT_STARTED test')
            tasks.append(parent)
        with self.assertRaises(ValueError):analyze(tasks)
        result=build_results(self.m,tasks,False)
        self.assertEqual(len(result['points']),48);self.assertEqual(len(result['cells']),192)
        self.assertEqual(sum(r['n_incomplete_pairs'] for r in result['ratios']),2160)
        self.assertEqual(result['bootstrap'],{})
        for c in result['cells']:
            self.assertIsNone(c['TaskTotal_ns']['median']);self.assertEqual(c['TaskTotal_ns']['n_scheduled'],c['TaskTotal_ns']['n_unstarted'])
    def test_statistics_failure_exclusion(self):
        p=self.m['workloads'][0];tasks=[]
        for mode in ('COLD','ONLINE'):
            for rep in range(3):
                for method in ('packed','repeated'):
                    e={'ordinal':len(tasks),'run_id':str(len(tasks)),'point_id':p['id'],'batch_id':BATCH_ID,'pair_id':mode+str(rep),
                       'method':method,'preprocess_mode':mode,'warmup':False,'repetition':rep}
                    r,_=unavailable(self.m,p,e,'RUNTIME_FAIL' if rep==2 else 'COMPLETE','synthetic')
                    r.update(execution_attempted=True,task_total_ns=100 if method=='packed' else 200,aggregate_cpu_ns=100,peak_rss_kib=1,phase_ns={k:1 for k in PHASES})
                    tasks.append(r)
        result=build_results({**self.m,'workloads':[p]},tasks,True)
        for r in result['ratios']:
            self.assertEqual(r['n_complete_pairs'],2);self.assertEqual(r['n_incomplete_pairs'],1);self.assertEqual(r['median_paired_ratio'],2)
        self.assertEqual(len(result['paired_rows']),4)
        self.assertEqual(len(result['bootstrap'][p['id']+'/COLD']['median_paired_ratio_resamples']),10000)

if __name__=='__main__':unittest.main(verbosity=2)
