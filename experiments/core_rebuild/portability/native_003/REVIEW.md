# Isolated native portability acceptance

Status: `PASS_ISOLATED_NATIVE_PORTABILITY_GATE`.

The new `checkout_001/` contains nine exact frozen native code files, the original
B0 pin manifest and 142 original XPIR source files checked against that manifest.
It does not contain manuscript files, historical raw observations or the measured
native executable. The official XPIR codeload request timed out; acquisition was
an explicitly recorded exact-pin copy of the existing original upstream tree.

Official Ubuntu noble-security `libssl-dev` and `libssl3t64`, both
`3.0.13-0ubuntu3.16 amd64`, were downloaded by host HTTPS. The Linux coordinator
independently verified the InRelease signature with the installed Ubuntu archive
keyring, the signed Packages.xz digest and the exact package identities, sizes and
SHA256 values before extraction. Extraction and all build/runtime outputs remain
under this directory. No system package was installed. The prior WSL stall and
stale `3.15` package 404 attempts remain in `native_001/` and `native_002/`.

The frozen builder and unit builder completed with the workspace-staged header
and library search environment. Actual dependencies contain six official
OpenSSL headers and no Sage fallback headers. The builder retains its original
conditional fallback flag. A separate loader readback retains paths containing
spaces and confirms that the new executable loads the staged `libcrypto.so.3`;
the frozen builder's legacy spaced-path parsing was not changed.

The unit gate and all 130 finite native functional tasks passed, including full
records, both padding layers, legal layouts, readonly mappings, invalid-domain
rejections and fresh-process fingerprint diagnostics. The functional timestamps
are explicitly excluded from performance analysis. No formal performance task was
rerun. The new executable has a distinct SHA256; original measured binary, freeze,
raw ledger and the nine original native code-file hashes were checked before and
after and remain unchanged.

Evidence: `portability_report.json`, official metadata under
`upstream_metadata_001/`, exact packages under `host_downloads_001/`, verified
package member lists under `dependencies_001/`, retained phase logs under `logs/`,
and the new build/unit/functional reports under `checkout_001/`.

This is a fresh source-root functional acceptance on the recorded host using
official staged dependencies. It is not acceptance of a clean operating-system
installation, byte-identical binaries across machines, security, failure
probabilities or new performance conclusions. Headers, libraries, packages and
native executables are not public vendoring candidates. Any public metadata
promotion must preserve its provenance and review its recorded local paths.
