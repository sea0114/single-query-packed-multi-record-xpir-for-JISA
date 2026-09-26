"""Exact B0 build; measurement-only overlay, no mutation of pinned sources."""
from pathlib import Path
import subprocess,json,hashlib,difflib,re,os
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
BUILD=HERE/"build"
UP=ROOT/"native_xpir/upstream"
LOG=ROOT/"revision_notes/B0_logs"
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    BUILD.mkdir(exist_ok=True);LOG.mkdir(exist_ok=True)
    source=UP/"pir/replyGenerator/PIRReplyGeneratorNFL_internal.cpp"
    old=source.read_text()
    remove=['\tstd::cout<<"PIRReplyGeneratorNFL_internal: Finished importing the database in " << omp_get_wtime() - start << " seconds" << std::endl;',
            '  printf( "PIRReplyGeneratorNFL_internal: Global reply generation took %f (omp)seconds\\n", omp_get_wtime() - start);']
    new=old
    for line in remove:
        assert new.count(line)==1,line
        new=new.replace(line,"  // B0 measurement overlay: omit incidental timer formatting/output.")
    overlay=BUILD/source.name;overlay.write_text(new)
    (LOG/"measurement_overlay.diff").write_text("".join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=str(source.relative_to(ROOT)),tofile="B0_build_overlay.cpp")))
    flags=["-std=gnu++11","-O2","-g","-fopenmp","-maes","-mavx2","-DSHARED_C","-include","cstdint",
           "-I"+str(UP),"-I"+str(UP/"crypto"),"-I"+str(source.parent),"-idirafter","/var/tmp/s4f-sage/include"]
    names=["crypto/AbstractPublicParameters.cpp","crypto/HomomorphicCrypto.cpp","crypto/LatticesBasedCryptosystem.cpp",
        "crypto/NFLLWE.cpp","crypto/NFLLWEPublicParameters.cpp","crypto/NFLlib.cpp","crypto/NFLParams.cpp",
        "crypto/prng/fastrandombytes.cpp","crypto/prng/randombytes.cpp","crypto/prng/crypto_stream_salsa20_amd64_xmm6.s",
        "pir/replyGenerator/GenericPIRReplyGenerator.cpp","pir/dbhandlers/DBHandler.cpp","pir/dbhandlers/DBGenerator.cpp"]
    sources=[HERE/"worker.cpp",overlay]+[UP/n for n in names]
    commands=[];objects=[];deps=set()
    with (LOG/"build.log").open("w") as log:
        for s in sources:
            obj=BUILD/(s.stem+".o");dep=Path(str(obj)+".d")
            cmd=["g++",*flags,"-MD","-MF",str(dep),"-c",str(s),"-o",str(obj)]
            commands.append(cmd);subprocess.run(cmd,stdout=log,stderr=log,check=True);objects.append(obj)
        link=["-Wl,--wrap=crypto_stream_salsa20_amd64_xmm6","-lboost_thread","-lboost_system","-lgmpxx","-lgmp","-lmpfr","-l:libcrypto.so.3","-pthread"]
        binary=BUILD/"b0_worker"
        cmd=["g++",*flags,*map(str,objects),*link,"-o",str(binary)]
        commands.append(cmd);subprocess.run(cmd,stdout=log,stderr=log,check=True)
    # GCC escapes spaces in dependency paths; split using shlex.
    import shlex
    for dep in BUILD.glob("*.o.d"):
        text=dep.read_text().replace("\\\n","")
        for x in shlex.split(text.split(": ",1)[1]):
            p=Path(x)
            if p.is_file():deps.add(p.resolve())
    ldd=subprocess.check_output(["ldd",str(binary)],text=True)
    libs={Path(x).resolve() for x in re.findall(r"(?:=> )?(/[^\s]+)",ldd) if Path(x).is_file()}
    compiler=Path(subprocess.check_output(["which","g++"],text=True).strip()).resolve()
    record={"backend_commit":"75c5e912cbe6a8d5bf5ac0f3f74a665b0265c78c","compiler":str(compiler),"compiler_sha256":sha(compiler),
        "compiler_version":subprocess.check_output(["g++","--version"],text=True),"compile_flags":flags,"link_flags":link,
        "PGO":False,"LTO":False,"MULTI_THREAD":False,"same_binary_both_methods":True,"binary":str(binary.relative_to(ROOT)),
        "binary_sha256":sha(binary),"upstream_files":{str(p.relative_to(ROOT)):sha(p) for p in sorted(UP.rglob("*")) if p.is_file()},
        "source_hashes":{str(p):sha(p) for p in sources},"dependencies":{str(p):sha(p) for p in sorted(deps)},
        "libraries":{str(p):sha(p) for p in sorted(libs)},"ldd":ldd,
        "overlay_base_sha256":sha(source),"overlay_sha256":sha(overlay),"commands":commands}
    (LOG/"build_environment.json").write_text(json.dumps(record,indent=2)+"\n")
    print("B0 native build PASS; identical binary for both methods; no performance run")
if __name__=="__main__":main()
