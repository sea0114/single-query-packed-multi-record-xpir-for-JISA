# Build and validate the native implementation

The native runner requires Linux x86-64 with AES/AVX2, GNU C++ with OpenMP, Boost thread/system, GMP/GMPXX, MPFR and OpenSSL 3 development files. The recorded environment used Python 3.12 and GNU C++ 13.3.0 on Ubuntu 24.04/WSL2. Typical Ubuntu packages are `build-essential libboost-thread-dev libboost-system-dev libgmp-dev libmpfr-dev libssl-dev`.

From the repository root, acquire the pinned XPIR source:

```bash
python3 -B scripts/verify_release.py
python3 -B scripts/fetch_upstream.py --root .
```

The fetcher checks commit `75c5e912cbe6a8d5bf5ac0f3f74a665b0265c78c` and all 142 file hashes in [upstream-build-environment.json](../manifests/upstream-build-environment.json) before creating `native_xpir/upstream/`. The manifest SHA256 is `19acb1fe7b90ada0160b403c4fff0b52645b1ca2dd54db9c7cf0ab8e118128c1`. Existing destinations are refused. `--check-contract-only` verifies the contract without downloading; `--git-repository PATH` uses an existing repository containing the same pinned commit and tree. Original upstream notices remain intact.

Follow the [core build and validation commands](../experiments/core_rebuild/README.md#commands-for-a-new-independent-run) to create a new run identity, probe resources, build the executable/unit test and run the functional gate. Compilation records actual source, compiler, flags, headers and linked-library hashes. The builder uses `-DMULTI_THREAD` and the original upstream block-parallel reply implementation.

The measured build used a conditional OpenSSL header fallback at `/var/tmp/s4f-sage/include`. When that directory is absent, the builder uses the configured system development headers. A separate recorded build passed the unit gate and all 130 functional tasks with official Ubuntu OpenSSL `3.0.13-0ubuntu3.16` headers/runtime; see [validation](validation.md). Those records identify their original build environment, not identical binaries on a new machine.

For the lightweight analysis unit suite, which does not execute native code:

```bash
python3 -B -m unittest discover -s experiments/core_rebuild/tests -p 'test_analysis.py' -v
```

Source acquisition, compilation, functional validation and performance measurement are separate operations. New measurements use their own resource review, configuration, schedule and output directories as specified in the core README.
