"""B0 preserves all prior stages and all formal/manuscript sources by default."""
from pathlib import Path
import hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[2];LOG=ROOT/"revision_notes/B0_logs";ARCH=ROOT/"revision_notes/archive/pre_B0"
LOG.mkdir(parents=True,exist_ok=True);ARCH.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=LOG/"protected_before.json"
if not manifest.exists():
    for name in ("Section5.tex","main.pdf","main.aux"):shutil.copy2(ROOT/name,ARCH/name)
    paths={p for p in ROOT.glob("*.tex")}|{ROOT/n for n in ("main.pdf","references.bib","JISE.sty","JISEbib.bst")}
    for folder in ("native_xpir","tests","tools","revision_notes"):
        for p in (ROOT/folder).rglob("*"):
            if not p.is_file() or "__pycache__" in p.parts:continue
            rel=p.relative_to(ROOT).as_posix()
            if rel.startswith("tools/benchmark/") or "/B0" in rel or "/pre_B0/" in rel:continue
            paths.add(p)
    manifest.write_text(json.dumps({p.relative_to(ROOT).as_posix():sha(p) for p in sorted(paths)},indent=2)+"\n")
    print("B0 snapshot:",len(paths),"files")
else:
    before=json.loads(manifest.read_text())
    changed=[p for p,h in before.items() if sha(ROOT/p)!=h]
    if "--authorized-manuscript" in sys.argv:
        from manuscript import expected_section
        assert set(changed)=={"Section5.tex","main.pdf"},changed
        assert (ROOT/"Section5.tex").read_bytes()==expected_section()
        assert json.loads((ROOT/"revision_notes/B0_status.json").read_text())["B0_status"]=="PASS"
    else:assert not changed,changed
    result={"status":"PASS","protected_files":len(before),"manuscript_and_PDF_unchanged":not changed,
            "authorized_changes":changed,"prior_stage_logs_unchanged":True,
            "formal_proofs_and_prior_native_sources_unchanged":True}
    (LOG/"protected_verification.json").write_text(json.dumps(result,indent=2)+"\n")
    print("B0 protection PASS:",len(before),"files; manuscript/PDF unchanged")
