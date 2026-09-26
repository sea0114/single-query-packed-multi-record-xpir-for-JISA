"""Read-only native build/dependency check after the three functional smoke cases."""
from b2b_common import *
import subprocess,shutil
def main():
    b=read(LOG/'build_manifest.json');checks={}
    checks['binary']=sha(ROOT/b['binary'])==b['binary_sha256']
    for field in ('source_hashes','reused_adapters','unchanged_upstream_files'):
        checks[field]=all(sha(ROOT/n)==h for n,h in b[field].items())
    for field in ('dependencies','libraries'):
        checks[field]=all(Path(n).is_file() and sha(n)==h for n,h in b[field].items())
    compiler=Path(shutil.which('g++')).resolve()
    checks['compiler']=str(compiler)==b['compiler'] and sha(compiler)==b['compiler_sha256'] and subprocess.check_output(['g++','--version'],text=True)==b['compiler_version']
    checks['serial_native']=not b['MULTI_THREAD'] and not any('MULTI_THREAD' in flag for flag in b['compile_flags'])
    checks['PGO_LTO_unchanged']=not b['PGO'] and not b['LTO']
    write(LOG/'native_build_verification.json',dict(status='PASS' if all(checks.values()) else 'FAIL',checks=checks,dependencies=len(b['dependencies']),formal_observations=0))
    assert all(checks.values()),checks
    print(json.dumps({'native_build':'PASS','dependencies':len(b['dependencies'])}))
if __name__=='__main__':main()
