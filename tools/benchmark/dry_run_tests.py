"""Functional acceptance only. Never summarize or compare native timing values."""
import copy,json,sys,math
from collections import Counter,defaultdict
from pathlib import Path
from spec import *
from runner import run_task,load_manifest,unexecuted_row,environment_snapshot
from validate import validate
from analysis import analyze,describe,paired_ratio
def main():
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument("--manifest");ap.add_argument("--label",default="functional-v1");a=ap.parse_args()
    m=load_manifest(a.manifest) if a.manifest else json.loads((LOG/"draft_dry_manifest.json").read_text())
    out=LOG/a.label;out.mkdir(exist_ok=False)
    events=[];allrows=[];fingerprints=[];ordinal=0
    def run(rho,mode,method,inject=None,reverse=False):
        nonlocal ordinal
        p=point(7,257 if rho!=16 else 2048,rho)
        entry={"run_id":f"{a.label}-{ordinal:03}","pair_id":f"functional/{rho}/{mode}","point_id":p["id"],
               "ordinal":ordinal,"warmup":False,"method":method,"preprocess_mode":mode,"repetition":0}
        mm=copy.deepcopy(m)
        if inject=="timeout":mm["dry_run_caps"]["wall_timeout_ns"]=1_000_000_000
        parent,workers=run_task(mm,p,entry,out/f"{ordinal:03}",True,inject,reverse);ordinal+=1
        for row in workers+[parent]:validate(row)
        allrows.extend(workers+[parent]);status={"timeout":"TIMEOUT","resource":"RESOURCE_LIMIT","runtime":"RUNTIME_FAIL","wrong":"WRONG_OUTPUT"}.get(inject,"COMPLETE")
        assert parent["status"]==status,(inject,parent["status"],parent["failure_reason"])
        assert len(set(w["pid"] for w in workers))==len(workers)
        assert sum(len(w["cpu_affinity"]) for w in workers)<=2
        if len(workers)==2:assert set(workers[0]["cpu_affinity"]).isdisjoint(workers[1]["cpu_affinity"])
        assert parent["barrier_ready_count"]==len(workers)
        if status in ("COMPLETE","WRONG_OUTPUT"):
            assert parent["barrier_completion_count"]==len(workers) and parent["validation_released"]
            assert parent["task_start_ns"]==min(w["task_start_ns"] for w in workers)
            assert parent["task_end_ns"]==max(w["task_end_ns"] for w in workers)
            assert parent["task_total_ns"]==parent["task_end_ns"]-parent["task_start_ns"]
            assert parent["aggregate_cpu_ns"]==sum(w["cpu_user_ns"]+w["cpu_system_ns"] for w in workers)
            assert parent["peak_rss_kib"]==sum(w["peak_rss_kib"] for w in workers)
            assert parent["combined_query_bytes"]==sum(w["query_payload_bytes"] for w in workers)==7*131072*len(workers)
            assert parent["combined_reply_bytes"]==sum(w["reply_payload_bytes"] for w in workers)==131072*len(workers)
            assert all(w["release_ns"]==parent["barrier_release_ns"]<=w["task_start_ns"] for w in workers)
            assert min(w["phase_events"]["ValidationOverhead"]["begin"] for w in workers)>=parent["task_end_ns"]
            hashes=db_hashes(p["N"],p["ell_bits"],rho)
            for w in workers:
                assert (w["db_fixture_hash"],w["encoded_db_hash"])==hashes
                assert w["key_generation_calls"]==1 and w["query_encrypt_calls"]==7
                assert w["omp_max_threads"]==1 and w["observed_max_threads"]==1
                assert w["rng_calls"]==16
                assert sum(w["phase_ns"][k] for k in PHASES if k!="ValidationOverhead" and
                     not(mode=="ONLINE" and k in ("ConfigureServer","EncodeDB","ImportPreprocess")))<=w["task_total_ns"]
                fingerprints.append(w["key_fingerprint"])
            for i in range(len(workers)):
                assert (out/f"{ordinal-1:03}/worker{i}.stdout").stat().st_size==0,"upstream timer/log contamination"
        events.append({"rho_0":rho,"mode":mode,"method":method,"injection":inject,"reversed":reverse,"expected_status":status,"assertions":"PASS"})
    for rho in (8,12,16):
        for mode in ("COLD","ONLINE"):
            for method in ("packed","repeated"):run(rho,mode,method)
    for method in ("packed","repeated"):run(12,"ONLINE",method,reverse=True)
    run(8,"COLD","repeated","lag")
    for failure in ("timeout","resource","runtime","wrong"):run(8,"COLD","repeated",failure)
    assert len(fingerprints)==len(set(fingerprints)),"fresh native keys repeated"
    planned=json.loads((ROOT/m["schedule_file"]).read_text());assert len(planned)==4896
    groups=defaultdict(list)
    for e in planned:groups[(e["point_id"],e["preprocess_mode"],e["warmup"])].append(e)
    for (pid,mode,warmup),entries in groups.items():
        N=int(pid.split("_")[0][1:]);n=3 if warmup else {256:30,1024:30,4096:20,16384:10}[N]
        assert Counter(e["method"] for e in entries)=={"packed":n,"repeated":n}
        first=Counter(entries[k]["method"] for k in range(0,len(entries),2))
        assert abs(first["packed"]-first["repeated"])<=1
        for k in range(0,len(entries),2):assert entries[k]["pair_id"]==entries[k+1]["pair_id"]
    assert len(m["workloads"])==48 and len({p["id"] for p in m["workloads"]})==48
    pre=json.loads((ROOT/m["preflight_file"]).read_text())
    assert all(p["packed_query_bytes"]==2*1024**3 and p["repeated_query_bytes"]==4*1024**3 for p in pre if p["point_id"].startswith("N16384_"))
    assert max(p["repeated_estimated_resident_upper_bytes"] for p in pre)<m["resource_caps"]["aggregate_rss_bytes"]
    sample_entry={**planned[0],"batch_id":"synthetic-schema-test"}
    validate(unexecuted_row(m,m["workloads"][0],sample_entry,"RESOURCE_LIMIT","synthetic unstarted failure"))
    try:run_task(m,m["workloads"][0],sample_entry,out/"must-not-run-main",True)
    except ValueError:pass
    else:raise AssertionError("main point admitted to B0 dry-run")
    snapshot=environment_snapshot()
    assert "fresh Windows-side snapshot" in snapshot["windows_capture_policy"]
    dump(out/"environment_snapshot.json",snapshot)
    # Synthetic statistics checks only: no native timings are analyzed.
    d=describe([1,2,3,4],2);assert d["median"]==2.5 and d["Q1"]==1.75 and d["Q3"]==3.25 and d["n_failed"]==2
    b=paired_ratio([(1,2),(2,4),(3,6)]);assert b["median_paired_ratio"]==2 and b["CI95"]==[2,2]
    try:analyze(allrows)
    except ValueError:pass
    else:raise AssertionError("dry-run analysis not rejected")
    # Mutation and type guards.
    invalid=copy.deepcopy(allrows[0]);del invalid["phase_ns"]
    try:validate(invalid)
    except AssertionError:pass
    else:raise AssertionError("schema missing-field guard")
    testmanifest=out/"tampered.json";dump(testmanifest,m);testmanifest.with_suffix(".json.sha256").write_text("0"*64)
    try:load_manifest(testmanifest,False)
    except ValueError:pass
    else:raise AssertionError("immutable digest guard")
    result={"status":"PASS","timing_label":"DRY_RUN / NOT_FOR_ANALYSIS","formal_points_executed":0,
        "functional_parent_tasks":ordinal,"raw_rows":len(allrows),"unique_key_fingerprints":len(fingerprints),"checks":events,
        "acceptance":["ordered outputs + reverse order","independent Python fixture/encoded SHA256","balanced native phase endpoints",
            "validation starts after both timed intervals","separate PIDs + fresh keys + unchanged native RNG counts",
            "disjoint affinity, total core budget, actual 1 native thread","simultaneous release gate and actual-start timestamps",
            "TaskTotal=min(start) to max(end) with delayed-peer probe","exact bytes/CPU/RSS aggregation",
            "timeout/resource mock/runtime/wrong-output propagation","raw schema and immutable digest guard",
            "48-point matrix and preflight","4896-entry balanced pre-generated schedule",
            "synthetic analysis formula checks","dry-run exclusion from analysis","native stdout empty"],
        "tested_hashes":{str(p.relative_to(ROOT)):sha(p) for p in [HERE/n for n in ("worker.cpp","runner.py","validate.py","analysis.py","spec.py","dry_run_tests.py","build/b0_worker")]},
        "dry_artifact_directory":str(out.relative_to(ROOT)),"performance_claims":False}
    dump(LOG/"dry_run_acceptance.json",result);dump(out/"acceptance.json",result)
    print("B0 functional acceptance PASS:",ordinal,"tasks,",len(allrows),"rows. DRY_RUN / NOT_FOR_ANALYSIS. No performance summaries.")
if __name__=="__main__":main()
