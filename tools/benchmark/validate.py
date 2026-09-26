"""Required fields, types and timing/accounting semantics; no third-party dependency."""
import json,sys
from spec import PHASES,STATUSES
REQUIRED=["experiment_version","run_id","batch_id","warmup","ordinal","method","baseline_worker_id","workload","crypto",
 "backend_commit","build_hash","host_id","cpu_affinity","omp_threads","target_tuple","db_fixture_hash","encoded_db_hash",
 "preprocess_mode","phase_ns","task_total_ns","cpu_user_ns","cpu_system_ns","query_ciphertexts","reply_ciphertexts",
 "query_payload_bytes","reply_payload_bytes","peak_rss_kib","status","failure_reason","output_verified","sampler_label",
 "notes","record_type","timing_label","transport_bytes","layout_id","pid"]
MEASURES=["task_total_ns","cpu_user_ns","cpu_system_ns","query_ciphertexts","reply_ciphertexts",
          "query_payload_bytes","reply_payload_bytes","peak_rss_kib"]
def validate(row):
    assert all(k in row for k in REQUIRED),"missing required field"
    assert row["record_type"] in ("task","worker")
    assert row["status"] in STATUSES
    assert row["method"] in ("packed","repeated")
    assert row["preprocess_mode"] in ("COLD","ONLINE")
    assert row["timing_label"] in ("DRY_RUN / NOT_FOR_ANALYSIS","FORMAL")
    assert isinstance(row["warmup"],bool) and isinstance(row["output_verified"],bool)
    assert isinstance(row["ordinal"],int) and row["ordinal"]>=0
    assert row["transport_bytes"]=="NOT_MEASURED"
    assert row["workload"]["N"]>=2 and row["workload"]["alpha"] in (1,2)
    assert row["workload"]["rho_0"] in (8,12,16)
    assert row["crypto"]["n"]==4096 and row["crypto"]["Berr"]==200
    assert row["crypto"]["w"]==2*row["workload"]["rho_0"]
    assert len(row["target_tuple"])==2 and len(set(row["target_tuple"]))==2
    assert set(row["phase_ns"])==set(PHASES)
    for value in [row[k] for k in MEASURES]+list(row["phase_ns"].values()):
        assert value is None or (type(value) is int and value>=0),"measurement must be a nonnegative integer or null"
    if row["status"]=="COMPLETE":
        assert row["output_verified"] and row["failure_reason"]==""
        assert all(row[k] is not None for k in MEASURES)
        assert row["task_total_ns"]==row["task_end_ns"]-row["task_start_ns"]>0
        for k in ("db_fixture_hash","encoded_db_hash"):
            assert isinstance(row[k],str) and len(row[k])==64
        assert row["query_payload_bytes"]==row["query_ciphertexts"]*131072
        assert row["reply_payload_bytes"]==row["reply_ciphertexts"]*131072
    if row["record_type"]=="worker" and row["phase_events"]:
        assert set(row["phase_events"])==set(PHASES)
        for name,event in row["phase_events"].items():
            assert event["end"]>=event["begin"]>0
            assert row["phase_ns"][name]==event["end"]-event["begin"]
            if name=="ValidationOverhead":assert event["begin"]>=row["task_end_ns"]
            elif row["preprocess_mode"]=="ONLINE" and name in ("ConfigureServer","EncodeDB","ImportPreprocess"):
                assert event["end"]<=row["task_start_ns"]
            else:assert row["task_start_ns"]<=event["begin"]<=event["end"]<=row["task_end_ns"]
    if row["record_type"]=="task":
        for k in ("worker_ids","worker_pids","aggregate_cpu_ns","aggregate_peak_metric","combined_query_bytes","combined_reply_bytes"):
            assert k in row
        assert len(row["worker_ids"])==(1 if row["method"]=="packed" else 2)
        assert len(set(row["worker_pids"]))==len(row["worker_pids"])
        assert row["combined_query_bytes"]==row["query_payload_bytes"]
        assert row["combined_reply_bytes"]==row["reply_payload_bytes"]
    return True
def schema():
    props={k:{} for k in REQUIRED}
    for k in MEASURES:props[k]={"type":["integer","null"],"minimum":0}
    for k in ("warmup","output_verified"):props[k]={"type":"boolean"}
    for k in ("experiment_version","run_id","batch_id","backend_commit","build_hash","host_id","failure_reason","sampler_label","layout_id"):
        props[k]={"type":"string"}
    for k in ("db_fixture_hash","encoded_db_hash"):props[k]={"type":["string","null"],"pattern":"^[a-f0-9]{64}$"}
    props.update(status={"enum":STATUSES},method={"enum":["packed","repeated"]},
        record_type={"enum":["worker","task"]},preprocess_mode={"enum":["COLD","ONLINE"]},
        timing_label={"enum":["DRY_RUN / NOT_FOR_ANALYSIS","FORMAL"]},
        transport_bytes={"const":"NOT_MEASURED"},ordinal={"type":"integer","minimum":0},
        phase_ns={"type":"object","required":PHASES,"properties":{k:{"type":["integer","null"],"minimum":0} for k in PHASES},"additionalProperties":False})
    return {"$schema":"https://json-schema.org/draft/2020-12/schema","title":"B0 completed task and worker",
        "type":"object","required":REQUIRED,"properties":props,
        "allOf":[{"if":{"properties":{"record_type":{"const":"task"}}},
                  "then":{"required":["worker_ids","worker_pids","aggregate_cpu_ns","aggregate_peak_metric","combined_query_bytes","combined_reply_bytes"]}}]}
if __name__=="__main__":
    count=0
    for file in sys.argv[1:]:
        for line in open(file):
            validate(json.loads(line));count+=1
    print("Schema and semantic validation PASS:",count,"rows")
