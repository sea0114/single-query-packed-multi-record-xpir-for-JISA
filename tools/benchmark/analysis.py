"""B1 analysis skeleton. Rejects all B0 dry-run rows; no B0 performance analysis."""
import statistics as s,random,json,argparse
from pathlib import Path
from collections import defaultdict
from spec import ANALYSIS_SEED
def quantile(values,p):
    v=sorted(values);h=(len(v)-1)*p;a=int(h);return v[a]+(v[min(a+1,len(v)-1)]-v[a])*(h-a)
def describe(values,n_failed):
    base={"n_complete":len(values),"n_failed":n_failed}
    if not values:return {**base,**{k:None for k in ("median","Q1","Q3","IQR","min","max","mean","sample_stddev")}}
    q1,q3=quantile(values,.25),quantile(values,.75)
    return {**base,"median":s.median(values),"Q1":q1,"Q3":q3,"IQR":q3-q1,
            "min":min(values),"max":max(values),"mean":s.mean(values),"sample_stddev":s.stdev(values) if len(values)>1 else None}
def paired_ratio(pairs):
    ratios=[repeated/packed for packed,repeated in pairs]
    if not ratios:return {"n_pairs":0,"median_paired_ratio":None,"CI95":None}
    rng=random.Random(ANALYSIS_SEED)
    boot=[s.median(rng.choices(ratios,k=len(ratios))) for _ in range(10000)]
    return {"n_pairs":len(ratios),"median_paired_ratio":s.median(ratios),
            "CI95":[quantile(boot,.025),quantile(boot,.975)],"resamples":10000,"seed":ANALYSIS_SEED}
def analyze(rows):
    if any(r["timing_label"]!="FORMAL" for r in rows):raise ValueError("DRY_RUN / NOT_FOR_ANALYSIS cannot enter analysis")
    if any(r.get("environment_valid",True) is False for r in rows):raise ValueError("invalid environment batch; retain but do not selectively analyze")
    if any(r["record_type"]=="task" and r["warmup"] and r["status"]!="COMPLETE" for r in rows):raise ValueError("failed warmup: whole batch invalid")
    groups=defaultdict(list);pairs=defaultdict(dict)
    for r in rows:
        if r["record_type"]!="task" or r["warmup"]:continue
        w=r["workload"];key=(w["N"],w["ell_bits"],w["rho_0"],r["preprocess_mode"],r["method"])
        groups[key].append(r)
        pair=pairs[key[:-1]+(r["batch_id"],r["pair_id"])]
        if r["method"] in pair:raise ValueError("duplicate task/pair; cannot double-count")
        pair[r["method"]]=r
    summaries={"/".join(map(str,k)):describe([r["task_total_ns"] for r in v if r["status"]=="COMPLETE"],
                                            sum(r["status"]!="COMPLETE" for r in v)) for k,v in groups.items()}
    ratio_groups=defaultdict(list);incomplete=defaultdict(int)
    for k,v in pairs.items():
        key=k[:4]
        if set(v)=={"packed","repeated"} and all(r["status"]=="COMPLETE" for r in v.values()):
            ratio_groups[key].append((v["packed"]["task_total_ns"],v["repeated"]["task_total_ns"]))
        else:incomplete[key]+=1
    ratios={"/".join(map(str,k)):{**paired_ratio(ratio_groups[k]),"n_incomplete_pairs":incomplete[k]} for k in set(ratio_groups)|set(incomplete)}
    return {"TaskTotal_ns":summaries,"actual_completed_task_paired_ratios":ratios,"outlier_filter":"NONE"}
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("jsonl",nargs="+");p.add_argument("--out",required=True);p.add_argument("--batch-status",required=True);a=p.parse_args()
    batch=json.load(open(a.batch_status))
    if not batch["environment_valid"]:raise SystemExit("whole batch marked environment invalid")
    incident=Path(a.batch_status).parent/"environment_invalid_incident.json"
    if incident.exists():raise SystemExit("whole-batch environment incident recorded; no selective analysis")
    rows=[json.loads(line) for file in a.jsonl for line in open(file)]
    with open(a.out,"x") as f:json.dump(analyze(rows),f,indent=2)
