# Radix-packed multi-record retrieval

This research artifact accompanies **Radix-Packed Multi-Record Retrieval over an XPIR-Style RLWE Interface**. It specifies ordered multi-record recovery by radix digits, conditional integer no-wrap correctness, and single-challenge index privacy under a distribution-specific PLWE assumption. Native execution and the formal sampler are **not** identified. The experiments compare completed tasks with concurrent, same-profile repeated XPIR on one WSL2 host.

Read the [paper](paper/pdf/main.pdf), [supplement](paper/pdf/supplement.pdf), [methodology](docs/methodology.md), and [limitations](docs/limitations.md). The manuscript is an editorial draft: journal-specific formatting and author declarations remain to be confirmed.

| Capability | Inputs and platform | Release validation |
|---|---|---|
| Recompute archived results | Included compressed data; Python 3.12.3 for exact historical replay | 120 cells, 360 median/interval values and 960,000 bootstrap values reproduced exactly; 68 arithmetic rows and 540 follow-up measured pairs checked |
| Recreate figures and paper | Matplotlib 3.10.9; TeX Live 2026, latexmk, BibTeX | New presentation matched archived numbers; original figure bytes also matched on the recorded Windows plotting environment |
| Build and validate native code | Linux x86-64 with AES/AVX2, compiler and libraries; pinned XPIR source download | Fresh build and 208 functional-only tasks / 448 workers passed; six adapter rejection checks passed |
| Collect new measurements | New host/build identity, resource agreement and newly frozen configuration | **Not performed by this release.** Old configuration pins must not be bypassed or reused with new binaries |

## Quick start: archived results

Run commands from this repository's root in a fresh checkout. Use Python 3.12.3 for the historical exact replay. Python 3.14.4 was separately used for presentation and packaging checks; other versions are not certified. Matplotlib and mpmath can be installed in your own virtual environment using `python -m pip install -r requirements-analysis.txt`. Ubuntu may first require its `python3-venv` package. Native code is unnecessary for replay.

```bash
git clone https://github.com/sea0114/single-query-packed-multi-record-xpir-for-JISA.git
cd single-query-packed-multi-record-xpir-for-JISA
python3 -B scripts/verify_release.py
python3 -B scripts/unpack_data.py
python3 -B scripts/verify_release.py --data
python3 -B artifact/scripts/recompute_accounting.py --out artifact/results/release_accounting_01
python3 -B scripts/check_accounting_portability.py --replay-dir artifact/results/release_accounting_01
```

The arithmetic replay produces 68 rows and exact sufficient-screen checks. Its frozen validator reports `DIFFERENCE` on Linux solely because its historical TeX reference has CRLF line endings. The following portability check must report `PASS_NUMERICAL_AND_TABLE_CONTENT`; it accepts **only** CRLF/LF differences, preserves the original report and changes no numerical input. Do not ignore other failures.

Continue with the original estimators and independent output directories:

```bash
python3 -B artifact/scripts/recompute_historical.py --out artifact/results/release_historical_01
python3 -B artifact/scripts/analyze_b3.py --config artifact/configs/B3_local_protocol.json --raw artifact/raw/B3-formal-v1 --out artifact/results/release_sensitivity_capacity_01
python3 -B artifact/scripts/render_historical_displays.py --out artifact/results/release_displays_01 --replay-dir artifact/results/release_historical_01
python3 -B scripts/present_results.py --out presentation_check
```

Expected historical status is `PASS`, with six exact targets and no differences. The follow-up analyzer reports `COMPLETE`, 1,404 successful tasks, zero unstarted tasks and descriptive inference only. The presentation command uses the checked archived references; it does not resample, combine experiments or change estimates. Compare `presentation_check/display_data.json` and the TeX/PDF displays with `paper/generated/`.

Every `--out` must be unused. Failed or partial outputs should be retained for diagnosis; choose a new name after resolving the cause. The versioned data archive is 28,726,108 bytes compressed and restores 230,566,247 bytes of data/reference evidence; exact bytes and SHA256 are in [data-archives.json](manifests/data-archives.json). No private original-workspace path is needed. Unpacking validates all members before writing and refuses different existing files. A checksum is an integrity check, not proof of scientific validity.

## Figure and table reproduction

See the complete [figure/table and evidence map](docs/experiment-map.md). Main Fig. 2 preserves all 96 primary cells; Table 5 provides four absolute-time examples; Table 6 keeps all 24 multiplicity cells; Table 7 covers all ten capacity cells. Table 8 is exact buffer accounting. The supplement retains the native frontier, full primary grid, cross-experiment overlap and sensitivity cells. Original archival identifiers occur in immutable evidence and are mapped to research names; they are not renamed inside frozen files.

## Build and functional checks

Follow [building.md](docs/building.md) for pinned upstream acquisition, compiler dependencies, fresh build identity and functional-only commands. The package distributes source and instructions, **not** old native executables or system libraries. The upstream source is obtained directly from its official repository and checked against all 142 original file hashes. An internet connection is needed for that source acquisition, but not for result replay after cloning.

The release validation used Ubuntu 24.04.1 under WSL2, GNU C++ 13.3.0 and one arithmetic thread per worker. Rebuilt binaries have new hashes and do not inherit old benchmark identity. The source/analysis/runner suites passed 81 tests; the encoding/correctness suites passed another 26. The native functional suite collects no performance observations. Detailed scope and platform differences are in [validation.md](docs/validation.md).

## Optional future measurements

The frozen runners are retained for provenance, not as a one-command portable benchmark. A new campaign requires an idle, exclusive host; explicitly agreed CPU/memory limits; a new configuration, build manifest and run identifier; predeclared cells, warmups, measured pairs, order and failure/stopping rules; and separate raw/results directories. Rebuilding changes the selector and intentionally invalidates old host/binary pins. Do not disable those checks, overwrite old observations, pool new samples with these experiments, or select sample counts from observed effects. No new campaign was run for this release.

## Citation, availability and licenses

Use [CITATION.cff](CITATION.cff), recording the exact Git commit from `git rev-parse HEAD`. The immutable [validated research package](https://github.com/sea0114/single-query-packed-multi-record-xpir-for-JISA/tree/bc13e9b67a5f9a8229664362be280cf81fbe43a8) is the artifact version cited by the manuscript. The data archive and machine-readable manifests are versioned in this repository, so cloning a specific commit retrieves the matching evidence. The existing repository history and public visibility are preserved.

Project-owned program contributions listed in [LICENSE_SCOPE.csv](LICENSE_SCOPE.csv) are licensed **GPL-3.0-or-later**, with the full GPLv3 text in [LICENSE](LICENSE). Frozen headers were not edited. Third-party terms and original copyrights remain intact; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Manuscript text, figures, documentation and data are **not automatically covered by the code license**, and no separate blanket license is granted here. Rights-uncertain upstream files are not redistributed in this package.

Report reproducibility problems in this repository's Issues with the commit, platform, command, new output path and error summary. Do not attach private keys, credentials or confidential datasets.
