"""MANIFEST_LEVEL_V1 verifier. Ordinary sidecars are forbidden, not trusted."""
from b2b_common import *
ROLES={'PROTOCOL','SCHEDULE','WORKLOAD','RESOURCE_MODEL','ENVIRONMENT','SOURCE','TOOL','BINARY','STATUS','OPEN_ISSUE','RELEASE_MANIFEST'}
REQUIRED=['B2_B_protocol.md','B2_B_concurrency_contract.md','B2_B_resource_preflight.md','B2_B_resource_preflight.json','B2_B_workload_matrix.md','B2_B_workload_matrix.json','B2_B_run_schedule.json','B2_B_statistics_plan.md','B2_B_open_issues.md','B2_B_freeze_status.json','B2_B_freeze_environment.json']
def verify_entries(manifest,root):
    errors=[];listed=set()
    for a in manifest['artifacts']:
        name=a['path'];p=Path(root)/name
        if name in listed:errors.append('duplicate: '+name)
        listed.add(name)
        if Path(name).is_absolute() or '..' in Path(name).parts or a['role'] not in ROLES:errors.append('invalid entry: '+name);continue
        if not p.is_file():errors.append('missing: '+name);continue
        if p.stat().st_size!=a['size'] or sha(p)!=a['sha256']:errors.append('digest/size: '+name)
    return errors,listed
def verify():
    m=read(MANIFEST);errors=[]
    if m['integrity_policy']!='MANIFEST_LEVEL_V1':errors.append('integrity policy')
    side=MANIFEST.with_suffix('.json.sha256')
    if not side.is_file() or side.read_text().split()[0]!=sha(MANIFEST):errors.append('release sidecar')
    e,listed=verify_entries(m,ROOT);errors+=e
    required={'revision_notes/'+x for x in REQUIRED}|{'tools/b2b/b2b_worker.cpp','tools/b2b/b2b_runner.py','tools/b2b/b2b_analyze.py','tools/b2b/verify_manifest.py',m['build']['binary'],m['build']['binary']+'.sha256'}
    if not required<=listed:errors.append('missing required indexed artifacts: '+str(sorted(required-listed)))
    reserved={MANIFEST.relative_to(ROOT).as_posix(),side.relative_to(ROOT).as_posix()}
    actual={p.relative_to(ROOT).as_posix() for p in scoped_files() if not p.relative_to(ROOT).as_posix().startswith(('revision_notes/B2_B_execution/','revision_notes/B2_B_execution_inputs/','revision_notes/B2_B_artifact_hashes.json'))}
    if actual!=listed|reserved:errors.append('extra/unlisted/missing freeze artifact: '+str(sorted(actual^(listed|reserved))))
    if reserved&listed:errors.append('manifest may not hash itself or its own sidecar')
    allowed_sides={m['build']['binary']+'.sha256',side.relative_to(ROOT).as_posix()}
    if {n for n in actual if n.endswith('.sha256')}!=allowed_sides:errors.append('ordinary or missing allowed sidecars')
    binary=ROOT/m['build']['binary']; bs=binary.with_name(binary.name+'.sha256')
    if not bs.is_file() or sha(binary)!=m['build']['binary_sha256'] or bs.read_text().split()[0]!=sha(binary):errors.append('binary seal')
    for name,h in m['parent_hashes'].items():
        if sha(ROOT/name)!=h:errors.append('parent anchor: '+name)
    from b2b_schedule import validate_schedule
    try:validate_schedule(read(ROOT/m['schedule']['path']),m['workloads'])
    except AssertionError as e:errors.append('schedule: '+str(e))
    if sha(ROOT/m['schedule']['path'])!=m['schedule']['sha256']:errors.append('schedule anchor')
    if errors:raise ValueError('\n'.join(errors))
    return {'status':'PASS','artifacts_verified':len(listed),'ordinary_sidecars':0,'manifest_sha256':sha(MANIFEST)}
if __name__=='__main__':print(json.dumps(verify()))
