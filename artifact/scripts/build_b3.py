#!/usr/bin/env python3
"""Build additive reconstructed B3 variants; never modify historical evidence."""
import argparse
import datetime
import difflib
import hashlib
import json
import pathlib
import re
import shlex
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
NATIVE = ROOT / 'artifact/native'
UP = ROOT / 'native_xpir/upstream'
LABEL = 'RECONSTRUCTED_SOURCE_VARIANT'
EXPECTED = {
    'tools/benchmark/worker.cpp': '4a3dcb9f2aac1fba80631493b6b1652f871917bd899baec4ef45a26b6fd68374',
    'tools/b2b/b2b_worker.cpp': 'e6ec7e7305934d6115fdee293fc31d05c3c69aebb0e9955addf9645b708edad1',
    'tools/benchmark/build/PIRReplyGeneratorNFL_internal.cpp': 'eccd748704eddd38f6a34261a75b1a436726be421843263325711338ca80050a',
}

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value, indent=2) + '\n', encoding='utf-8')

def replace(text, old, new):
    assert text.count(old) == 1, repr(old[:100])
    return text.replace(old, new, 1)

FIXTURE_TAIL = '''    require_fixture:
    if(kind=="zero")for(auto& row:r)std::fill(row.begin(),row.end(),0);
    else if(kind=="max")for(auto& row:r)std::fill(row.begin(),row.end(),255);
    else if(kind=="alternating")for(unsigned i=0;i<N;++i)for(size_t b=0;b<r[i].size();++b)r[i][b]=((i+b)%2)?0x55:0xaa;
    else if(kind!="pseudorandom")throw std::runtime_error("unknown public fixture");
    if(ell%8)for(auto& row:r)row.back()&=(1u<<(ell%8))-1;
    return r;'''.replace('    require_fixture:\n', '')

DOMAIN = '''        const std::string timing_label=job.get<std::string>("timing_label");
        const bool functional=timing_label=="FUNCTIONAL_ONLY_NOT_FOR_PERFORMANCE";
        timing_enabled=!functional;
        require(functional || timing_label=="B3_FORMAL" || timing_label=="B3_PILOT","B3 timing label");
        const std::string fixture_kind=job.get<std::string>("fixture","pseudorandom");
        require(functional || fixture_kind=="pseudorandom","nonfunctional fixture must be frozen pseudorandom");
        require(rho==8 && w==a*rho,"B3 profile");
        const bool cross=(a==2 && (N==1024||N==4096) && (ell==512||ell==2048));
        const bool capacity=(a==4 && N==1024 && (ell==4096||ell==8192||ell==12288||ell==16384||ell==65536));
        require(functional ? (N==8 && ell>0 && ell<=65536) : (cross || CAPACITY),"B3 allowed workload");
        m1::Layout layout(ell,rho,w,DEG);
        auto all_weights=m1::radix_weights(layout,a);m1::validate_weights(layout,all_weights);
        const std::string method=job.get<std::string>("method");
        require(method=="packed"||method=="repeated","method");
        std::vector<unsigned> targets;for(auto& v:job.get_child("targets"))targets.push_back(v.second.get_value<unsigned>());
        require(targets.size()==(method=="packed"?a:1),"request multiplicity");
        for(size_t k=0;k<targets.size();++k){
            require(targets[k]<N,"target range");
            for(size_t h=0;h<k;++h)require(targets[k]!=targets[h],"distinct ordered targets");
        }
        auto K=m1::radix_weights(layout,targets.size());m1::validate_weights(layout,K);
        const std::string mode=job.get<std::string>("preprocess_mode");
        require(mode=="COLD"||mode=="ONLINE","preprocess view");
'''

METADATA = '''        result.put("variant_label","RECONSTRUCTED_SOURCE_VARIANT");
        result.put("implementation_id","IMPLEMENTATION");
        result.put("fixture_id",fixture_kind+"-B3-common-seed-8c3f47282900cee8-v1");
        result.put("timing_label",timing_label);
'''

FUNCTIONAL_ERASE = '''            for(const char* key:{"task_start_ns","task_end_ns","task_total_ns","release_ns","preprocess_start_ns","preprocess_end_ns","cpu_user_ns","cpu_system_ns","peak_rss_kib","phase_ns","phase_events","clock_resolution_ns"})result.erase(key);
            result.put("timing_collected",false);'''

def derive(which):
    historical = 'tools/benchmark/worker.cpp' if which=='I1' else 'tools/b2b/b2b_worker.cpp'
    source=(ROOT/historical).read_text(encoding='utf-8')
    text=source
    if which=='I1':
        text=replace(text, '#include "crypto/NFLLWE.hpp"', '#include "m1_adapter.hpp"\n#include "crypto/NFLLWE.hpp"')
        text=replace(text, 'SEED=0x42305f4441544131ULL', 'SEED=0x8c3f47282900cee8ULL')
        text=replace(text, 'struct Span{', 'bool timing_enabled=true;\nuint64_t stamp(){return timing_enabled?now():0;}\nstruct Span{')
        text=replace(text, 's.begin=now();}~Timer(){s.end=now();', 's.begin=stamp();}~Timer(){s.end=stamp();')
        start=text.index('        unsigned N=job.get<unsigned>("N")')
        end=text.index('        auto raw=fixture(N,ell);', start)
        text=text[:start]+'''        unsigned N=job.get<unsigned>("N"),ell=job.get<unsigned>("ell_bits"),rho=job.get<unsigned>("rho_0"),a=job.get<unsigned>("alpha"),w=job.get<unsigned>("w");
        require(a==2,"I1 multiplicity");
'''+DOMAIN.replace('CAPACITY','false')+text[end:]
        text=replace(text, 'std::vector<unsigned> messages(N);for(size_t k=0;k<targets.size();k++)messages[targets[k]]=uint64_t(1)<<(rho*k);', 'std::vector<unsigned> messages(N);for(size_t k=0;k<targets.size();k++)messages[targets[k]]=static_cast<unsigned>(K[k]);')
        text=text.replace('prep.begin=now();','prep.begin=stamp();').replace('prep.end=now();','prep.end=stamp();')
        start=text.index('        auto inject=job.get<std::string>("inject","");')
        end=text.index('        rusage before{},after{};',start)
        text=text[:start]+text[end:]
        text=replace(text, 'uint64_t task_begin=now(),', 'uint64_t task_begin=stamp(),')
        text=replace(text, '        if(inject=="lag"){timespec delay{0,50000000};nanosleep(&delay,nullptr);} // Dry-run critical-path assertion only.\n', '')
        text=replace(text, 'uint64_t task_end=now();', 'uint64_t task_end=stamp();')
        text=replace(text, '            if(inject=="wrong")decoded[0][0]^=1;', '''            // B3: full coefficient checks are deliberately post-DONE/V.
            // The timed I1 extractor above remains the original J-field implementation.
            std::vector<std::vector<uint64_t>> expected_fields;
            for(auto target:targets)expected_fields.push_back(m1::segments(raw[target],layout));
            for(uint64_t block=0;block<L;++block){
                size_t size=client->publicParams.getCiphertextBitsize()/8;
                unsigned char* plain=reinterpret_cast<unsigned char*>(client->decrypt(reply->repliesArray[block],1,size,DEG*w/8));
                auto fields=m1::read_fields(plain,DEG,w);free(plain);
                for(uint64_t j=0;j<DEG;++j){
                    uint64_t expected_packed=0;
                    for(size_t k=0;k<targets.size();++k)expected_packed+=K[k]*expected_fields[k][block*DEG+j];
                    correct&=fields[j]<layout.t() && fields[j]==expected_packed;
                }
            }''')
        extra=METADATA.replace('IMPLEMENTATION','B3-I1')+'''        result.put("alpha",a);result.put("request_alpha",targets.size());result.put("rho_0",rho);result.put("w",w);
        result.put("N",N);result.put("ell_bits",ell);result.put("J",J);result.put("L",L);
        result.put("coefficient_checks",L*DEG);result.put("segment_checks",L*DEG*targets.size());result.put("record_checks",targets.size());
        result.put("all_coefficients_exact",correct);result.put("all_segments_exact",correct);result.put("padding_exact",correct);
        result.put("direct_weight_encryption",true);result.put("native_reply_calls",1);result.put("native_decrypt_calls",L);
        result.put("post_timing_validation_decrypt_calls",L);
        if(functional){
'''+FUNCTIONAL_ERASE+'''
        }
'''
        text=replace(text, '        write_json(argv[2],result);return correct?0:20;', extra+'        write_json(argv[2],result);return correct?0:20;')
    else:
        text=replace(text, '#include "../../native_xpir/m1_adapter.hpp"', '#include "m1_adapter.hpp"')
        start=text.index('        const bool functional=')
        end=text.index('        auto raw=fixture(N,ell);', start)
        text=text[:start]+'''        require(a==2||a==3||a==4,"I2 multiplicity");
'''+DOMAIN.replace('CAPACITY','capacity')+text[end:]
        text=replace(text, '        result.put("timing_label",functional?"FUNCTIONAL_ONLY_NOT_FOR_PERFORMANCE":"FORMAL");', METADATA.replace('IMPLEMENTATION','B3-I2')+'        result.put("post_timing_validation_decrypt_calls",0);')
    text=replace(text, 'DB fixture(unsigned N,unsigned ell){', 'DB fixture(unsigned N,unsigned ell,const std::string& kind){')
    text=replace(text, '    if(ell%8)for(auto& row:r)row.back()&=(1u<<(ell%8))-1;\n    return r;', FIXTURE_TAIL)
    text=replace(text, 'auto raw=fixture(N,ell);', 'auto raw=fixture(N,ell,fixture_kind);')
    text='// B3 '+which+': RECONSTRUCTED_SOURCE_VARIANT; original source protected.\n'+text
    target=NATIVE/(which+'_worker.cpp')
    write(target,text)
    write(NATIVE/(which+'_from_historical.diff'), ''.join(difflib.unified_diff(source.splitlines(True),text.splitlines(True),fromfile=historical,tofile=target.relative_to(ROOT).as_posix())))
    return target

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--build-id',default=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    args=parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+',args.build_id)
    for name,digest in EXPECTED.items():
        assert sha(ROOT/name)==digest, 'Historical source changed: '+name
    old=json.loads((ROOT/'revision_notes/B0_logs/build_environment.json').read_text())
    for name,digest in old['upstream_files'].items():
        assert sha(ROOT/name)==digest,name
    build=NATIVE/'build'/args.build_id
    build.mkdir(parents=True,exist_ok=False)
    sources={which:derive(which) for which in ('I1','I2')}
    flags=['-std=gnu++11','-O2','-g','-fopenmp','-maes','-mavx2','-DSHARED_C','-include','cstdint',
        '-I'+str(UP),'-I'+str(UP/'crypto'),'-I'+str(UP/'pir/replyGenerator'),'-I'+str(ROOT/'native_xpir')]
    legacy_include=pathlib.Path('/var/tmp/s4f-sage/include')
    if legacy_include.is_dir():flags.extend(['-idirafter',str(legacy_include)])
    links=['-Wl,--wrap=crypto_stream_salsa20_amd64_xmm6','-lboost_thread','-lboost_system','-lgmpxx','-lgmp','-lmpfr','-l:libcrypto.so.3','-pthread']
    names=['crypto/AbstractPublicParameters.cpp','crypto/HomomorphicCrypto.cpp','crypto/LatticesBasedCryptosystem.cpp','crypto/NFLLWE.cpp','crypto/NFLLWEPublicParameters.cpp','crypto/NFLlib.cpp','crypto/NFLParams.cpp','crypto/prng/fastrandombytes.cpp','crypto/prng/randombytes.cpp','crypto/prng/crypto_stream_salsa20_amd64_xmm6.s','pir/replyGenerator/GenericPIRReplyGenerator.cpp','pir/dbhandlers/DBHandler.cpp','pir/dbhandlers/DBGenerator.cpp']
    common=[ROOT/'tools/benchmark/build/PIRReplyGeneratorNFL_internal.cpp']+[UP/name for name in names]
    compiler=pathlib.Path(shutil.which('g++')).resolve()
    commands=[]; objects=[];binaries={}
    def run(command,log):
        commands.append(command)
        log.write(('COMMAND '+shlex.join(command)+'\n').encode());log.flush()
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    with (build/'build.log').open('xb') as log:
        for source in common:
            obj=build/(source.stem+'.o')
            run([str(compiler),*flags,'-MD','-MF',str(obj)+'.d','-c',str(source),'-o',str(obj)],log)
            objects.append(obj)
        for which,source in sources.items():
            obj=build/(which+'_worker.o');binary=build/(which+'_worker')
            run([str(compiler),*flags,'-MD','-MF',str(obj)+'.d','-c',str(source),'-o',str(obj)],log)
            run([str(compiler),*flags,str(obj),*map(str,objects),*links,'-o',str(binary)],log)
            binaries[which]={'path':binary.relative_to(ROOT).as_posix(),'sha256':sha(binary),'ldd':subprocess.check_output(['ldd',str(binary)],text=True)}
    libraries={}
    for d in binaries.values():
        for s in re.findall(r'(?:=> )?(/[^\s]+)',d['ldd']):
            p=pathlib.Path(s)
            if p.is_file():libraries[str(p.resolve())]=sha(p)
    manifest={'status':'BUILT_NOT_FUNCTIONALLY_VALIDATED','variant_label':LABEL,'build_id':args.build_id,
        'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'backend_commit':'75c5e912cbe6a8d5bf5ac0f3f74a665b0265c78c',
        'historical_sources':EXPECTED,'source_hashes':{p.relative_to(ROOT).as_posix():sha(p) for p in [*sources.values(),*common,ROOT/'native_xpir/m1_adapter.hpp']},
        'compiler':str(compiler),'compiler_sha256':sha(compiler),'compiler_version':subprocess.check_output([str(compiler),'--version'],text=True),
        'compile_flags':flags,'link_flags':links,'PGO':False,'LTO':False,'MULTI_THREAD':False,'PERF_TIMERS':False,
        'libraries':libraries,'binaries':binaries,'commands':commands,'fixture_seed':'0x8c3f47282900cee8','crypto_randomness':'unchanged native OS-seeded Salsa20; no secret state stored',
        'timing_note':'I1 retains J-field extraction; I2 all-field extraction. Extra I1 full coefficient validation decrypts occur after every worker DONE; never part of TaskTotal.',
        'formal_observations_executed':0}
    write(build/'build_manifest.json',manifest)
    write(NATIVE/'current_build.json',{'build_manifest':(build/'build_manifest.json').relative_to(ROOT).as_posix(),'sha256':sha(build/'build_manifest.json'),'binaries':binaries})
    print(json.dumps({'status':'BUILT_NOT_FUNCTIONALLY_VALIDATED','build_manifest':str(build/'build_manifest.json'),'binaries':binaries},indent=2))

if __name__=='__main__':main()
