# Native build and functional validation

## Current core runner

Use [core_rebuild/README.md](../experiments/core_rebuild/README.md) for the new runner's exact build and functional commands, dependencies, writes and independent output identities. The only promoted historical dependency metadata is the unchanged `revision_notes/B0_logs/build_environment.json`, SHA256 `19acb1fe7b90ada0160b403c4fff0b52645b1ca2dd54db9c7cf0ab8e118128c1`, which pins 142 upstream files. Once present in a checkout, `scripts/fetch_upstream.py --root .` can verify/acquire the fixed official XPIR source without extracting the full old data archive. Source acquisition and native execution are separate actions; fetched upstream notices and file-specific rights gaps remain.

The isolated `native_003` build and 130-task functional gate passed using separately staged official Ubuntu OpenSSL `3.0.13-0ubuntu3.16` development headers and runtime, without consuming the historical Sage header fallback. The official codeload retry was unavailable, so this check used a fresh source copy whose 142 hashes matched the B0 pins. This is a new binary/dependency identity and did not rerun formal performance collection. The staged package files, system headers/libraries and native executables are excluded from publication. Portable frozen analysis and redraw need no native build; their actual acceptance is recorded in the core README.

## Retained historical build route

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

## Native support and functional evidence

The checked adapter requires `1 <= w <= 56` and exact radix weights `K_r=2^(rho_0*r)` no larger than `2^32-1`. `m1::encrypt_integer` verifies the integer fits the declared plaintext field and unsigned-integer API before one direct `client.encrypt(value,1)` call; it does not truncate a weight or create an encrypted one to scale afterward. The supported width is checked independently of algebraic radix capacity. All nine tested alpha=2/3/4, rho_0=8/12/16 combinations meet `t=B^alpha` and the zero-noise arithmetic screen `2*(t-1)<q`; six pass the current API. Profiles (3,16), (4,12), (4,16) exceed the direct-weight limit, and (4,16) also exceeds the width range. These are API restrictions, not security or reliability bounds.

The [frontier summary](../revision_notes/B2_A_feasibility_frontier.json) records exact weights, width status, rejection reasons and evidence paths. The historical two-record profiles each passed 82 encrypted cases (246 total); each of the three supported additional profiles passed ten. The separate capacity-focused functional suite passed 208 tasks with 448 fresh-key processes, including ordered and reversed targets, equal contents at distinct indices, maximum digits, partial-segment and full-block padding, and lengths 32767/32768/32769 across J=n. [data-layout.md](data-layout.md) indexes those archived results. These finite checks are distinct from paired latency trials and do not estimate a native failure probability.

## Historical editorial snapshot

The current checkout contains implementation and reproduction materials. Earlier [paper sources](https://github.com/sea0114/single-query-packed-multi-record-xpir-for-JISA/tree/552da1aa2902a2a0497a60cc93537665644047ef/paper) and [submission materials](https://github.com/sea0114/single-query-packed-multi-record-xpir-for-JISA/tree/552da1aa2902a2a0497a60cc93537665644047ef/submission) remain in historical commit 552da1aa. They contain an older security argument and display arrangement, and are not the current manuscript. Historical build records do not establish current JISA compliance or completed author declarations. No manuscript build is needed for the current native, analysis or figure/table reproduction routes.
