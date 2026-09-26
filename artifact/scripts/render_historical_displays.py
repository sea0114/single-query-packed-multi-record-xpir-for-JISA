#!/usr/bin/env python3
"""Rebuild historical displays additively, without executing the old workflow.

The sealed generator has no separate pure render functions: its main combines
rendering, source checks and supplement writes, and importing it sets a sealed
MPLCONFIGDIR. This wrapper instead verifies that source against its original
manifest, extracts only its rendering statements through AST, and executes
that block with a new output directory and an exclusive save function. It
never imports the old module, calls old main(), resamples, or writes there.

Requires matplotlib; optional pdftotext enables PDF-text comparison. Visual QA
of the regenerated PNG/PDF remains explicit even if numerical checks pass.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = 'revision_notes/manuscript_integration/build_displays.py'
MANIFEST = 'revision_notes/manuscript_integration_manifest.json'
MANIFEST_SHA = '9bc0a98d0e4920a3c87fa219e88ba5569f1ccd6e0dbf59cac8dc4da3872cb6eb'
OLD_DIR = 'revision_notes/manuscript_integration/displays'
OLD_DATA = 'revision_notes/manuscript_integration/display_data.json'


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def verified_original_inputs():
    require(sha(ROOT / MANIFEST) == MANIFEST_SHA, 'Original integration manifest anchor mismatch')
    index = {entry['path']: entry for entry in read(ROOT / MANIFEST)['artifacts']}
    needed = [ORIGINAL, OLD_DATA] + [OLD_DIR + '/' + name for name in
                ('F1_primary.pdf', 'F1_primary.tex', 'T1_frontier.tex', 'T2_scalability.tex')]
    hashes = {MANIFEST: MANIFEST_SHA}
    for name in needed:
        require(name in index and sha(ROOT / name) == index[name]['sha256'], 'Sealed display/source mismatch: ' + name)
        hashes[name] = index[name]['sha256']
    original_data = read(ROOT / OLD_DATA)
    expected_sources = {
        'revision_notes/B2_A_feasibility_frontier.json',
        'revision_notes/B1_primary_audit/paired_ratio_recomputed.json',
        'revision_notes/B2_B_result_audit/scaling_audit.json',
    }
    require(set(original_data['sources']) == expected_sources, 'Unexpected original display source mapping')
    for name, digest in original_data['sources'].items():
        require(sha(ROOT / name) == digest, 'Audited numerical input mismatch: ' + name)
        hashes[name] = digest
    return original_data, hashes


def rendering_block(source):
    """Lift only the sealed rows/plot/table block, excluding all old I/O setup."""
    parsed = ast.parse(source, filename=ORIGINAL)
    mains = [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name == 'main']
    require(len(mains) == 1, 'Expected one archived main definition')
    body = mains[0].body
    start = [i for i, node in enumerate(body) if isinstance(node, ast.Assign)
             and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
             and node.targets[0].id == 'rows' and isinstance(node.value, ast.List) and not node.value.elts]
    end = [i for i, node in enumerate(body) if isinstance(node, ast.Expr)
           and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
           and node.value.func.id == 'save' and node.value.args
           and isinstance(node.value.args[0], ast.Constant) and node.value.args[0].value == 'display_data.json']
    require(len(start) == len(end) == 1 and start[0] < end[0], 'Archived render block boundaries changed')
    block = body[start[0]:end[0]+1]
    for node in ast.walk(ast.Module(body=block, type_ignores=[])):
        require(not isinstance(node, (ast.Import, ast.ImportFrom)), 'Unexpected import inside render block')
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                require(node.func.id not in ('main', 'open', 'exec', 'eval', 'compile', '__import__'), 'Unexpected unsafe render call')
            elif isinstance(node.func, ast.Attribute):
                require(node.func.attr not in ('write_text', 'write_bytes', 'unlink', 'remove', 'mkdir', 'rmdir', 'rename', 'replace'), 'Unexpected direct mutation in render block')
    module = ast.fix_missing_locations(ast.Module(body=block, type_ignores=[]))
    return compile(module, ORIGINAL + '::render_block_only', 'exec'), dict(
        first_line=block[0].lineno, last_line=block[-1].end_lineno,
        statement_count=len(block), old_main_called=False, old_module_imported=False,
        excluded='Old source setup, claim-registry loop, output-directory setup, supplement generation, print and main invocation.')


def verify_replay_values(data, replay_dir):
    path = replay_dir / 'cells.json'
    status_path = replay_dir / 'status.json'
    status = read(status_path)
    require(status['status'] == 'PASS' and status['difference_count'] == 0, 'Historical numerical replay did not pass')
    cells = read(path)
    lookup = {(c['experiment_id'], c['alpha'], c['N'], c['ell_bits'], c['rho0'], c['view']): c for c in cells}
    require(len(lookup) == len(cells) == 120, 'Expected complete 120-cell replay')
    for source in data['F1']:
        cell = lookup['B1', 2, source['N'], source['ell_bits'], source['rho_0'], source['mode']]
        require(source['median_paired_ratio'] == cell['separate_median_evidence']['median_paired_ratio'], 'Figure median vs replay mismatch')
        require(source['CI95'] == cell['CI95'], 'Figure CI vs replay mismatch')
    for source in data['T2']:
        for alpha in (2, 3, 4):
            cell = lookup['B2B', alpha, source['N'], source['ell_bits'], 8, source['view']]
            require(source['R' + str(alpha)] == cell['separate_median_evidence']['median_paired_ratio'], 'Table 4 median vs replay mismatch')
            require(source['CI95_R' + str(alpha)] == cell['CI95'], 'Table 4 CI vs replay mismatch')
    return dict(status='PASS_EXACT_NUMERIC_MAPPING', figure_cells=96, multiplicity_cells=24,
                files=[dict(path=str(p), sha256=sha(p)) for p in (path, status_path)],
                frontier='Nine rows supplied by the separately hash-verified finite-correctness frontier, not timing replay.')


def pdf_text_check(original, regenerated, requested_program):
    program = requested_program or shutil.which('pdftotext')
    if not program:
        return dict(status='NOT_RUN_TOOL_UNAVAILABLE', command='pdftotext -layout INPUT -', visual_check_required=True)
    results = []
    for path in (original, regenerated):
        process = subprocess.run([program, '-layout', str(path), '-'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if process.returncode:
            return dict(status='NOT_RUN_TOOL_ERROR', executable=program, returncode=process.returncode,
                        error=process.stderr.decode('utf-8', errors='replace'), visual_check_required=True)
        results.append(process.stdout.decode('utf-8', errors='replace'))
    equal = ' '.join(results[0].split()) == ' '.join(results[1].split())
    return dict(status='MATCH_NORMALIZED_TEXT' if equal else 'TEXT_DIFFERENCE_REQUIRES_REVIEW', executable=program,
                original_text=results[0], regenerated_text=results[1],
                normalization='Collapse whitespace only; does not validate plotted coordinates.', visual_check_required=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--replay-dir', type=Path, default=ROOT / 'artifact/results/historical_replay_verified')
    parser.add_argument('--pdftotext', help='Optional explicit path to Poppler pdftotext')
    args = parser.parse_args()
    output = args.out.resolve()
    require(output.is_relative_to((ROOT / 'artifact/results').resolve()), 'Output must be under artifact/results')
    require(not output.exists(), 'Exclusive output required: never overwrite any old results')
    data, hashes = verified_original_inputs()
    numerical_check = verify_replay_values(data, args.replay_dir.resolve())
    code, extraction = rendering_block((ROOT / ORIGINAL).read_text(encoding='utf-8'))
    output.mkdir(parents=True, exist_ok=False)
    plot_dir = output / 'displays'
    plot_dir.mkdir()
    os.environ['MPLCONFIGDIR'] = str(output / 'plot_config')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import ft2font
    written = []
    def save(name, text):
        path = (output / name).resolve()
        require(path.is_relative_to(output) and path.parent.exists(), 'Render save escaped new output')
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(text + '\n')
        written.append(path.relative_to(output).as_posix())
    env = dict(ROOT=ROOT, json=json, sha=sha, save=save, plt=plt, out=plot_dir,
        b1=read(ROOT / 'revision_notes/B1_primary_audit/paired_ratio_recomputed.json'),
        b2=read(ROOT / 'revision_notes/B2_B_result_audit/scaling_audit.json'),
        frontier=read(ROOT / 'revision_notes/B2_A_feasibility_frontier.json')['cells'])
    exec(code, env)
    require(set(written) == {'displays/T1_frontier.tex', 'displays/F1_primary.tex', 'displays/T2_scalability.tex', 'display_data.json'}, 'Unexpected render outputs')
    require(read(output / 'display_data.json') == data, 'Regenerated source/numeric display data mismatch')
    table_checks = {name: (plot_dir / name).read_bytes() == (ROOT / OLD_DIR / name).read_bytes()
                    for name in ('T1_frontier.tex', 'T2_scalability.tex')}
    require(all(table_checks.values()), 'Historical table transcription differs')
    figure_tex = plot_dir / 'F1_primary.tex'
    expected_original_tex = (ROOT / OLD_DIR / 'F1_primary.tex').read_text(encoding='utf-8')
    require(figure_tex.read_text(encoding='utf-8') == expected_original_tex, 'Figure wrapper unexpectedly changed')
    new_pdf_ref = (plot_dir / 'F1_primary.pdf').relative_to(ROOT).as_posix()
    old_pdf_ref = OLD_DIR + '/F1_primary.pdf'
    require(expected_original_tex.count(old_pdf_ref) == 1, 'Expected exactly one original figure path')
    # These are the only two authorized wrapper changes. Plot values, CI bars,
    # glyphs, labels and table contents are generated by the sealed render block.
    old_caption_phrase = 'the preregistered pointwise'
    new_caption_phrase = 'the pointwise'
    require(expected_original_tex.count(old_caption_phrase) == 1, 'Expected one historical caption phrase')
    new_wrapper = expected_original_tex.replace(old_pdf_ref, new_pdf_ref).replace(old_caption_phrase, new_caption_phrase)
    figure_tex.write_text(new_wrapper, encoding='utf-8', newline='\n')
    original_pdf, new_pdf = ROOT / OLD_DIR / 'F1_primary.pdf', plot_dir / 'F1_primary.pdf'
    pdf_compare = pdf_text_check(original_pdf, new_pdf, args.pdftotext)
    require(all(sha(ROOT / name) == digest for name, digest in hashes.items()), 'Sealed input changed during rendering')
    report = dict(status='NUMERICAL_AND_TABLE_CHECKS_PASS_VISUAL_QA_PENDING', new_observations=0, statistics_recomputed=False,
        original_manifest_sha256=MANIFEST_SHA, original_generator_sha256=hashes[ORIGINAL],
        generator_reuse=extraction, numerical_mapping=numerical_check, T1_T2_bytes_identical=table_checks,
        F1_wrapper_changes=[
            {'kind':'OUTPUT_PATH_REDIRECTION','old':old_pdf_ref,'new':new_pdf_ref},
            {'kind':'CAPTION_ONLY_CORRECTION','old':old_caption_phrase,'new':new_caption_phrase,
             'reason':'Describe the frozen analysis without suggesting a public preregistration; no change to numbers, intervals or graphical elements.'}],
        PDF_bytes_identical=sha(original_pdf)==sha(new_pdf), PDF_text_comparison=pdf_compare,
        PDF_byte_identity_required=False,
        PDF_variation_note='Same plot source/data does not guarantee byte identity across Matplotlib, FreeType, font or PDF backend versions. Metadata dates are disabled by the original plot code.',
        visual_qa='PENDING: inspect regenerated F1_primary.png/PDF and compiled manuscript table layout; numeric/text checks are not visual validation.',
        versions={'python':sys.version,'matplotlib':matplotlib.__version__,'freetype':ft2font.__freetype_version__},
        input_hashes=hashes, wrapper_sha256=sha(__file__), command_argv=sys.argv)
    save('render_report.json', json.dumps(report, indent=2, ensure_ascii=False))
    artifact_index = [dict(path=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size, sha256=sha(p))
                      for p in sorted(output.rglob('*')) if p.is_file()]
    save('source_and_output_manifest.json', json.dumps(dict(schema='M1_M7_HISTORICAL_DISPLAY_REBUILD_V1',
        inputs=hashes, numerical_replay=numerical_check['files'], artifacts=artifact_index), indent=2))
    print(json.dumps({k:report[k] for k in ('status','new_observations','statistics_recomputed','T1_T2_bytes_identical','PDF_bytes_identical')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
