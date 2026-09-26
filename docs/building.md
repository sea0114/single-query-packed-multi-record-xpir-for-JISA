# Build and validate

Run in an independent clone, after `scripts/unpack_data.py`. The original frozen builder writes shared derived worker sources and `artifact/native/current_build.json` as well as the requested build directory. Never use it in an archival workspace. No old binary is bundled.

Linux x86-64 requires AES and AVX2, GNU C++/OpenMP, Boost development headers and thread/system libraries, GMP/GMPXX, MPFR and OpenSSL 3 development files. The validated host was Ubuntu 24.04.1 under WSL2 with GNU C++ 13.3.0. Typical Ubuntu dependency packages are `build-essential libboost-thread-dev libboost-system-dev libgmp-dev libmpfr-dev libssl-dev`; package versions on other systems may differ and have not been validated here. No package installer is run by these scripts.

```bash
python3 -B scripts/fetch_upstream.py --root .
python3 -B artifact/scripts/build_b3.py --build-id release_build_01
python3 -B artifact/tests/test_b3_native.py --run-id release_functional_01
```

The fetcher contacts only the fixed official XPIR codeload URL, checks the original build manifest and all 142 exact file hashes, rejects unsafe archive members and refuses an existing destination. It does not execute downloaded source. Its optional `--git-repository PATH` route verifies the same commit/tree in an existing local repository. Retain partial outputs after a failure; do not overwrite or rewrite pins. The original notices are fetched unchanged; see `THIRD_PARTY_NOTICES.md` for individual source-rights gaps.

The builder uses GNU++11, `-O2 -g -fopenmp -maes -mavx2 -DSHARED_C -include cstdint`. It records compiler, source, linked-library hashes and commands in the new build manifest. If `/var/tmp/s4f-sage/include` exists, the frozen builder adds it as a fallback include directory; the validated host had this historical OpenSSL-header fallback. A clean machine should use compatible system OpenSSL 3 development headers. That alternate header environment has not been independently built here. Rebuilding never certifies identical historical binaries or benchmark conditions.

The complete native suite runs 208 tasks and 448 fresh-key workers, checks ordered records, equal-valued records at distinct indices, maximum digits, full padding and block boundaries, and strips performance fields. `--quick` runs only four tasks and is not full coverage. Run identifiers should be simple unused leaf names. For public-domain rejection guards:

```bash
g++ -std=gnu++11 -O2 -include cstdint -I native_xpir -I native_xpir/upstream scripts/check_native_guards.cpp -o artifact/native/build/release_build_01/check_native_guards
artifact/native/build/release_build_01/check_native_guards
```

Expected result is six rejected invalid domains and one supported profile. This is a functional check, not an encrypted failure-probability experiment.

The inspected unit suites do not run native benchmarks:

```bash
python3 -B -m unittest discover -s artifact/tests -p 'test_*.py' -v
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
```

The first has 81 tests and requires Linux's process/resource facilities. The second has 26 tests and needs mpmath 1.3.0. Use discovery: the legacy correctness test's standalone main writes an old report path. Do not recursively execute every file with `test` in its name.

To build the manuscript, use TeX Live 2026 with `elsarticle` v3.5, latexmk and BibTeX:

```bash
cd paper
latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build/local_01 main.tex supplement.tex
```

The output directory is new and separate from sources. A flattened source bundle for Editorial Manager is supplied under `submission/` once verified; it is a packaging option, not proof of JISA's final journal-specific format requirements. Bibliography uses the provisional numerical Elsevier style. Funding, conflicts and CRediT remain unfilled by author instruction.
