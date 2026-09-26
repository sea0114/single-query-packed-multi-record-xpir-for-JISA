"""B2 functional binary, compiled additively against unchanged pinned sources."""
from b2b_common import *
import platform,re,shlex,shutil,subprocess

def main():
    m=read(NOTES/'B0_benchmark_manifest.json');old=read(NOTES/'B0_logs/build_environment.json')
    build=HERE/'build'
    if build.exists():assert not any(build.iterdir()),'Refuse to overwrite an existing build'
    else:build.mkdir()
    compiler=Path(shutil.which('g++')).resolve()
    version=subprocess.check_output(['g++','--version'],text=True)
    assert str(compiler)==m['build']['compiler'] and sha(compiler)==m['build']['compiler_sha256'] and version==m['build']['compiler_version']
    for name,digest in old['upstream_files'].items():assert sha(ROOT/name)==digest,name
    for name,digest in m['build']['libraries'].items():assert sha(Path(name))==digest,name
    up=ROOT/'native_xpir/upstream'
    base=up/'pir/replyGenerator/PIRReplyGeneratorNFL_internal.cpp'
    overlay=ROOT/'tools/benchmark/build/PIRReplyGeneratorNFL_internal.cpp'
    assert sha(base)==m['build']['overlay_base_sha256'] and sha(overlay)==m['build']['overlay_sha256']
    text=base.read_text()
    for line in ['\tstd::cout<<"PIRReplyGeneratorNFL_internal: Finished importing the database in " << omp_get_wtime() - start << " seconds" << std::endl;',
                 '  printf( "PIRReplyGeneratorNFL_internal: Global reply generation took %f (omp)seconds\\n", omp_get_wtime() - start);']:
        assert text.count(line)==1;text=text.replace(line,'  // B0 measurement overlay: omit incidental timer formatting/output.')
    assert text==overlay.read_text() # Existing immutable output-only overlay, no arithmetic edits.
    flags=['-std=gnu++11','-O2','-g','-fopenmp','-maes','-mavx2','-DSHARED_C','-include','cstdint',
           '-I'+str(up),'-I'+str(up/'crypto'),'-I'+str(base.parent),'-idirafter','/var/tmp/s4f-sage/include']
    names=['crypto/AbstractPublicParameters.cpp','crypto/HomomorphicCrypto.cpp','crypto/LatticesBasedCryptosystem.cpp',
           'crypto/NFLLWE.cpp','crypto/NFLLWEPublicParameters.cpp','crypto/NFLlib.cpp','crypto/NFLParams.cpp',
           'crypto/prng/fastrandombytes.cpp','crypto/prng/randombytes.cpp','crypto/prng/crypto_stream_salsa20_amd64_xmm6.s',
           'pir/replyGenerator/GenericPIRReplyGenerator.cpp','pir/dbhandlers/DBHandler.cpp','pir/dbhandlers/DBGenerator.cpp']
    sources=[HERE/'b2b_worker.cpp',overlay]+[up/n for n in names]
    commands=[];objects=[]
    with (LOG/'build.log').open('x') as log:
        for source in sources:
            obj=build/(source.stem+'.o');cmd=[str(compiler),*flags,'-MD','-MF',str(obj)+'.d','-c',str(source),'-o',str(obj)]
            commands.append(cmd);subprocess.run(cmd,stdout=log,stderr=log,check=True);objects.append(obj)
        links=['-Wl,--wrap=crypto_stream_salsa20_amd64_xmm6','-lboost_thread','-lboost_system','-lgmpxx','-lgmp','-lmpfr','-l:libcrypto.so.3','-pthread']
        binary=build/'b2b_worker';cmd=[str(compiler),*flags,*map(str,objects),*links,'-o',str(binary)]
        commands.append(cmd);subprocess.run(cmd,stdout=log,stderr=log,check=True)
    deps=set()
    for dep in build.glob('*.o.d'):
        for name in shlex.split(dep.read_text().replace('\\\n','').split(': ',1)[1]):
            if Path(name).is_file():deps.add(Path(name).resolve())
    ldd=subprocess.check_output(['ldd',str(binary)],text=True)
    libs={Path(p).resolve() for p in re.findall(r'(?:=> )?(/[^\s]+)',ldd) if Path(p).is_file()}
    manifest={'backend_commit':COMMIT,'compiler':str(compiler),'compiler_version':version,'compiler_sha256':sha(compiler),
       'compile_flags':flags,'link_flags':links,'PGO':False,'LTO':False,'MULTI_THREAD':False,
       'binary':binary.relative_to(ROOT).as_posix(),'binary_sha256':sha(binary),'purpose':'B2-B performance binary; no formal observations during freeze',
       'source_hashes':{p.relative_to(ROOT).as_posix():sha(p) for p in sources},
       'unchanged_upstream_files':old['upstream_files'],'dependencies':{str(p):sha(p) for p in sorted(deps)},
       'libraries':{str(p):sha(p) for p in sorted(libs)},'ldd':ldd,'commands':commands,
       'reused_adapters':{name:sha(ROOT/name) for name in ['native_xpir/m1_adapter.hpp','native_xpir/s4_n/support.hpp']},
       'output_only_overlay':{'base':base.relative_to(ROOT).as_posix(),'base_sha256':sha(base),'overlay':overlay.relative_to(ROOT).as_posix(),'overlay_sha256':sha(overlay),'difference':'Two timing output statements omitted; verified exact existing B0 replacement. No arithmetic change.'},
       'derivation':'B1 phase/endpoints and native pipeline; B2-A generalized exact validation; no arithmetic optimization.',
       'n':4096,'q':CRYPTO['q'],'Berr':200,'sampler_PRNG':'Same native XPIR sampler and /dev/urandom-seeded Salsa20; observer only forwards unchanged calls.',
       'S4_N_sampler_inventory':'revision_notes/S4_N_native_sampler_inventory.md','new_encrypted_tasks_executed_by_build':0}
    write(LOG/'build_manifest.json',manifest)
    print(json.dumps({'build':'PASS','binary_sha256':sha(binary),'source_files':len(sources),'dependencies':len(deps)}))

if __name__=='__main__':main()

