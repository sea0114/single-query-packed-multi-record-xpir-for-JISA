#!/usr/bin/env python3
"""Synthetic scheduling/integrity unit tests; no native measurements."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
from b3_common import CAPS, POLICIES, cells
from execute_b3 import validate_protocol, validate_host, planned_tasks, relative_file, validate_output, exception_task, ART

def example():
    candidates=cells(include_multiblock=True)
    selected=[candidates[0],candidates[-1]]
    config={'config_status':'FROZEN_BEFORE_FORMAL','formal_budget_seconds':5400,'session_break_seconds':30,
        'caps':deepcopy(CAPS),'resource_policies':deepcopy(POLICIES),'sampling':{'sessions':3,'warmup_pairs_per_cell_session':3,'measured_pairs_per_cell_session':10},
        'cells':deepcopy(selected),'binaries':{'I1':{'path':'synthetic/I1','sha256':'0'*64},'I2':{'path':'synthetic/I2','sha256':'1'*64}},
        'frozen_files':{'synthetic/unit_test_only':'2'*64},'schedule':[]}
    for cell in selected:
        for session in range(1,4):
            for phase,count in (('warmup',3),('measured',10)):
                for round_number in range(count):
                    config['schedule'].append({'study':cell['study'],'cell_id':cell['cell_id'],'session_id':session,'phase':phase,'round':round_number,
                        'pair_id':f'{cell["study"]}_s{session}_{phase}_{round_number}',
                        'method_order':['packed','repeated'] if round_number%2==0 else ['repeated','packed']})
    return config

class ScheduleTests(unittest.TestCase):
    def setUp(self):self.config=example()
    def invalid(self,edit,message):
        edit(self.config)
        with self.assertRaisesRegex(ValueError,message):validate_protocol(self.config,check_files=False)
    def test_complete_design(self):
        result=validate_protocol(self.config,check_files=False)
        self.assertEqual((result['cells'],result['pairs'],result['tasks']),(2,78,156))
        self.assertEqual(len(result['study_session_groups']),6)
    def test_planned_task_order_and_unique_ids(self):
        expected=planned_tasks(self.config['schedule'])
        self.assertEqual(len({t['task_id'] for t in expected}),156)
        for i,entry in enumerate(self.config['schedule']):
            self.assertEqual([t['method'] for t in expected[2*i:2*i+2]],entry['method_order'])
    def test_duplicate_pair_is_rejected(self):
        self.invalid(lambda c:c['schedule'][1].update(pair_id=c['schedule'][0]['pair_id']),'Duplicate pair')
    def test_missing_measured_pair_is_rejected(self):
        self.invalid(lambda c:c['schedule'].pop(),'Wrong pair count')
    def test_warmup_after_measured_is_rejected(self):
        def edit(c):c['schedule'][2],c['schedule'][3]=c['schedule'][3],c['schedule'][2]
        self.invalid(edit,'Warmup after measured')
    def test_session_return_is_rejected(self):
        self.invalid(lambda c:c['schedule'].insert(14,c['schedule'].pop(0)),'cannot recur')
    def test_duplicate_round_is_rejected(self):
        self.invalid(lambda c:c['schedule'][1].update(round=0),'Duplicate round')
    def test_same_method_twice_is_rejected(self):
        self.invalid(lambda c:c['schedule'][0].update(method_order=['packed','packed']),'both methods exactly once')
    def test_unbalanced_order_is_rejected(self):
        def edit(c):
            for e in c['schedule']:
                if e['phase']=='measured':e['method_order']=['packed','repeated']
        self.invalid(edit,'not balanced')
    def test_altered_workload_is_rejected(self):
        self.invalid(lambda c:c['cells'][0].update(L=2),'Cell parameters differ')
    def test_unknown_cell_is_rejected(self):
        self.invalid(lambda c:c['schedule'][0].update(cell_id='missing'),'Unknown scheduled cell')
    def test_study_cell_mismatch_is_rejected(self):
        self.invalid(lambda c:c['schedule'][0].update(study='M5'),'study/cell mismatch')
    def test_unsafe_pair_id_is_rejected(self):
        self.invalid(lambda c:c['schedule'][0].update(pair_id='../escape'),'Invalid pair_id')
    def test_unsafe_session_id_is_rejected(self):
        self.invalid(lambda c:c['schedule'][0].update(session_id='../escape'),'Invalid session_id')
    def test_unfrozen_config_is_rejected(self):
        self.invalid(lambda c:c.update(config_status='DRAFT'),'must be frozen')
    def test_changed_budget_is_rejected(self):
        self.invalid(lambda c:c.update(formal_budget_seconds=5401),'5400 seconds')
    def test_changed_caps_is_rejected(self):
        self.invalid(lambda c:c['caps'].update(parent_rss_bytes=1),'caps differ')
    def test_changed_resource_policy_is_rejected(self):
        self.invalid(lambda c:c['resource_policies']['R1'].update(packed_affinity=[0]),'policies differ')
    def test_changed_sampling_design_is_rejected(self):
        self.invalid(lambda c:c['sampling'].update(measured_pairs_per_cell_session=9),'Reviewed design requires')
    def test_explicit_sampling_required(self):
        self.invalid(lambda c:c.pop('sampling'),'Explicit frozen sampling')
    def test_relative_paths_do_not_escape(self):
        for path in ('../outside','/absolute'):
            with self.assertRaises(ValueError):relative_file(path)
    def test_new_run_ids_allowed_only_as_immediate_children(self):
        self.assertEqual(validate_output(ART/'raw/B3-another-run').name,'B3-another-run')
        for path in (ART/'raw/other-run',ART/'raw/B3-nested/child',ART/'B3-other'):
            with self.assertRaises(ValueError):validate_output(path)
    def test_exception_metadata_can_be_analyzed_without_fabricated_times(self):
        from analyze_b3 import analyze
        config=self.config;config['synthetic_fixture']=True
        entry=config['schedule'][0];cell=config['cells'][0]
        row=exception_task(cell,entry,entry['method_order'][0],entry['pair_id']+'_packed',0,'B3-synthetic-unit-only','0'*64,'1'*64,'synthetic-boot',RuntimeError('synthetic test'))
        self.assertEqual(row['experiment_id'],'B3')
        self.assertEqual(row['run_id'],'B3-synthetic-unit-only')
        self.assertIsNone(row['task_total_ns'])
        row['timing_label']='SYNTHETIC_UNIT_ONLY'
        result=analyze(config,[row],[],'0'*64,synthetic=True)
        self.assertEqual(result['failed_tasks'],1)
        self.assertEqual(result['unstarted_tasks'],155)
        self.assertEqual(result['complete_tasks'],0)
    def test_host_identity(self):
        host={'cpu_model':'AMD Ryzen 7 3700X 8-Core Processor','os_release':'ID=ubuntu\n','kernel':'6.6.87.2-microsoft-standard-WSL2',
            'allowed_affinity':list(range(16)),'boot_id':'synthetic-unit-test-boot'}
        self.assertEqual(validate_host(host)['status'],'PASS')
        altered={**host,'boot_id':'different'}
        self.assertEqual(validate_host(altered,host)['status'],'FAIL')
        self.assertEqual(validate_host({**host,'allowed_affinity':[0,2]})['status'],'FAIL')
        self.assertEqual(validate_host({**host,'kernel':'bare-metal-linux'})['status'],'FAIL')

if __name__=='__main__':unittest.main(verbosity=2)
