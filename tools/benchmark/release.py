"""Final non-performance audit and artifact hashes, after PDF visual verification."""
import json,re,hashlib,subprocess,sys
from pathlib import Path
from manuscript import expected_section
ROOT=Path(__file__).resolve().parents[2];LOG=ROOT/"revision_notes/B0_logs"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    raw=p.read_bytes()
    return raw.decode("utf-16" if raw.startswith((b"\xff\xfe",b"\xfe\xff")) else "utf-8-sig",errors="replace")
def main():
    manifest=ROOT/"revision_notes/B0_benchmark_manifest.json";m=json.loads(manifest.read_text())
    assert sha(manifest)==manifest.with_suffix(".json.sha256").read_text().split()[0]
    assert manifest.read_bytes()==(ROOT/"revision_notes/B0_frozen"/(m["experiment_version"]+".json")).read_bytes()
    assert all(sha(ROOT/p)==h for p,h in m["frozen_files"].items()),"frozen files changed"
    acceptance=json.loads((LOG/"dry_run_acceptance.json").read_text())
    assert acceptance["status"]=="PASS" and acceptance["formal_points_executed"]==0
    assert "frozen-acceptance" in acceptance["dry_artifact_directory"]
    assert all(sha(ROOT/p)==h for p,h in acceptance["tested_hashes"].items())
    protected=json.loads((LOG/"protected_before.json").read_text())
    changed=[p for p,h in protected.items() if sha(ROOT/p)!=h]
    assert set(changed)=={"Section5.tex","main.pdf"},changed
    assert (ROOT/"Section5.tex").read_bytes()==expected_section()
    labels=lambda p:set(re.findall(r"\\newlabel\{([^}]+)\}",p.read_text()))
    assert labels(ROOT/"main.aux")==labels(ROOT/"revision_notes/archive/pre_B0/main.aux")
    text=" ".join(read(LOG/"main-extracted.txt").split())
    assert "benchmark protocol is frozen before formal measurements" in text
    assert "Cold and online costs are reported separately" in text
    latex=read(LOG/"latex-pass2.txt")
    assert "Output written on main.pdf" in latex
    assert not re.search(r"undefined references|Reference .* undefined|Citation .* undefined|^!",latex,re.M)
    visual=json.loads((LOG/"visual_review.json").read_text());assert visual["status"]=="PASS"
    raw_files=list(LOG.glob("**/raw.jsonl"));raw_rows=0
    for file in raw_files:
        for line in file.read_text().splitlines():
            row=json.loads(line);assert row["timing_label"]=="DRY_RUN / NOT_FOR_ANALYSIS";raw_rows+=1
    assert not list((ROOT/"revision_notes").glob("B1_run_*")),"unexpected B1 execution"
    results={"status":"PASS","manifest_sha256":sha(manifest),"protected_files":len(protected),
        "authorized_manuscript_changes":changed,"all_prior_stage_artifacts_unchanged":True,
        "formal_sources_unchanged":True,"labels_preserved":True,"formal_points_executed":0,
        "all_B0_raw_rows_labelled_NOT_FOR_ANALYSIS":True,"raw_rows_including_development_runs":raw_rows,
        "acceptance_tasks":acceptance["functional_parent_tasks"],"acceptance_rows":acceptance["raw_rows"],
        "visual_review":"PASS","main_pdf_sha256":sha(ROOT/"main.pdf")}
    (LOG/"release_checks.json").write_text(json.dumps(results,indent=2)+"\n")
    (LOG/"protected_verification.json").write_text(json.dumps({k:v for k,v in results.items() if k in
        ("status","protected_files","authorized_manuscript_changes","all_prior_stage_artifacts_unchanged","formal_sources_unchanged")},indent=2)+"\n")
    paths={ROOT/"Section5.tex",ROOT/"main.pdf"}
    for directory in (ROOT/"tools/benchmark",LOG,ROOT/"revision_notes/B0_frozen"):
        paths.update(p for p in directory.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    paths.update(p for p in (ROOT/"revision_notes").glob("B0_*") if p.is_file())
    target=LOG/"artifact_hashes.json";paths.discard(target)
    target.write_text(json.dumps({p.relative_to(ROOT).as_posix():sha(p) for p in sorted(paths)},indent=2)+"\n")
    print("B0 release PASS; protected prior files, immutable freeze, dry-run-only evidence and PDF verified.")
if __name__=="__main__":main()
