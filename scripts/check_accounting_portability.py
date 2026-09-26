#!/usr/bin/env python3
"""Classify only CRLF/LF differences after the unchanged frozen arithmetic replay.

SPDX-License-Identifier: GPL-3.0-or-later
"""
from pathlib import Path
import argparse,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--replay-dir',type=Path,required=True);a=ap.parse_args()
    p=a.replay_dir.resolve();assert p.is_relative_to(ROOT/'artifact/results')
    report=json.loads((p/'recompute_report.json').read_text())
    c=report['comparisons'];assert c['grid_byte_identical'] and c['all_exact_screens_identical']
    got=(p/'payload_table.tex').read_bytes();reference=(ROOT/'artifact/generated/payload_table.tex').read_bytes()
    assert got.replace(b'\r\n',b'\n')==reference.replace(b'\r\n',b'\n'),'Difference is not solely CRLF/LF'
    result={'status':'PASS_NUMERICAL_AND_TABLE_CONTENT','frozen_replay_status':report['status'],'reference_tex_sha256':hashlib.sha256(reference).hexdigest(),'new_tex_sha256':hashlib.sha256(got).hexdigest(),'tex_byte_identical':got==reference,'only_difference':'NONE' if got==reference else 'CRLF/LF line endings','rows':report['rows'],'original_replay_report_unchanged':True,'native_observations':0}
    with (p/'portability_check.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result))
if __name__=='__main__':main()
