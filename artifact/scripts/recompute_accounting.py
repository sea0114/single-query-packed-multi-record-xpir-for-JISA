"""Recompute exact accounting into a NEW directory without altering sealed outputs."""
from pathlib import Path
import argparse,csv,json,hashlib
from capacity_accounting import ROOT,build_rows,render_table

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();out=args.out.resolve()
    if not out.is_relative_to((ROOT/'artifact/results').resolve()):raise ValueError('Output must be under artifact/results')
    rows,screens,inputs=build_rows(ROOT)
    out.mkdir(parents=True,exist_ok=False)
    with (out/'full_grid.csv').open('x',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (out/'payload_table.tex').write_text(render_table(rows),encoding='utf-8')
    original=json.loads((ROOT/'artifact/results/accounting/correctness_screens.json').read_text())
    comparisons={
        'grid_byte_identical':(out/'full_grid.csv').read_bytes()==(ROOT/'artifact/results/accounting/full_grid.csv').read_bytes(),
        'table_byte_identical':(out/'payload_table.tex').read_bytes()==(ROOT/'artifact/generated/payload_table.tex').read_bytes(),
        'all_exact_screens_identical':screens==original['screens']}
    report=dict(status='PASS' if all(comparisons.values()) else 'DIFFERENCE',new_native_observations=0,
        comparisons=comparisons,rows=len(rows),screens=screens,inputs=inputs,
        generator_sha256=sha(Path(__file__).with_name('capacity_accounting.py')),recompute_sha256=sha(__file__),
        scope='Exact arithmetic and native representation only; no empirical timing or security certification.')
    (out/'recompute_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','comparisons','rows','new_native_observations')}))
    if report['status']!='PASS':raise SystemExit(1)

if __name__=='__main__':main()
