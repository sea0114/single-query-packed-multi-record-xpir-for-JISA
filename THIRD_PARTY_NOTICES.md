# Third-party source and dependency notices

This file records source provenance and license boundaries. It does not grant rights in third-party material or certify unresolved file-specific rights. The final release file manifest determines which materials are actually distributed.

## XPIR backend: obtained separately from its source repository

- Repository: <https://github.com/XPIR-team/XPIR>
- Commit: `75c5e912cbe6a8d5bf5ac0f3f74a665b0265c78c`
- Git tree: `dc9d04de9cab7f5e45cb27b49db61cc8cf61349e`
- Source verification contract: `manifests/upstream-build-environment.json`, SHA256 `19acb1fe7b90ada0160b403c4fff0b52645b1ca2dd54db9c7cf0ab8e118128c1`.

The release strategy excludes the complete `native_xpir/upstream/` tree and the historical XPIR ZIP from the distributed package. The provided acquisition tool downloads the pinned archive directly from GitHub's codeload service, or creates an archive from an existing local Git repository containing the exact commit and tree. It checks exactly 142 source-file hashes before creating a new `native_xpir/upstream/` directory for the frozen builder. It never downloads or authenticates a historical executable.

The original XPIR `LICENSE` describes a mixture of licenses. Most source files explicitly specify GNU GPL version 3 or later and retain copyrights of Carlos Aguilar Melchor, Joris Barrier, Marc-Olivier Killijian and any additional names/years in their respective headers. The fetched tree includes the original `LICENSE` and `GPL-3.0` text. Those original notices must remain intact.

Six files in `crypto/prng/` explicitly state public domain:

- `crypto_stream_salsa20.h`, `crypto_stream_salsa20_amd64_xmm6.s`, `randombytes.cpp`, `randombytes.h`: D. J. Bernstein.
- `fastrandombytes.cpp`, `fastrandombytes.h`: the original headers name Gim Güneysu, Tobias Oder, Thomas Pöppelmann and Peter Schwabe.

The fixed source has notice gaps that are not resolved by the acquisition tool: `FindGMP.cmake` refers to a missing `COPYING-CMAKE-SCRIPTS` for its BSD terms; the embedded old `crypto/NFLLWESecurityEstimator/lwe-estimator/` has no explicit local license; 24 additional files have no file-specific license header and are supported only by the repository's license context. Two such files, `pir/dbhandlers/DBHandler.cpp` and `crypto/NFLLWESecurityEstimated.hpp`, are required by the recorded native build. Fetching a repository does not establish rights that its notices leave unclear. Do not relabel these files as the present authors' original GPL code.

The old `estimator.pyc` is an actual tracked object in the pinned Git commit (mode `100644`, Git blob `1926e960cf28e7a3459fce9c9361cf0426a41c21`), not a generated file added by this project. It is fetched and hashed only to match the frozen 142-file source contract and is never executed by the acquisition tool. No source file is patched to make its hash match.

## External libraries

GMP, MPFR, Boost, OpenSSL, GCC runtime libraries, glibc, Python and Matplotlib remain external dependencies with their own licenses. A dependency name alone is not a complete license inventory: for example, the installed GMP and Boost packages include file-specific terms, and compiler runtime exceptions must not be omitted when applicable. Do not copy system headers/libraries, package environments, wheels or executables into the release without including the applicable package notices and checking that distribution's source requirements.

No dependency binaries are distributed in this release. The project GPL grant covers only authorized project-owned program contributions; manuscript text, datasets, plots, logs, photographs, third-party papers and other non-program materials do not automatically receive that grant.
