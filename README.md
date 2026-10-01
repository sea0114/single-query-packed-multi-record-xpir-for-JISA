# Radix-packed multi-record retrieval

This repository provides the implementation and evidence for **Radix-Packed Multi-Record Retrieval over an XPIR-Style RLWE Interface**. The manuscript specifies radix-packed ordered recovery, conditional integer no-wrap correctness, and single-challenge index privacy assuming IND-CPA security of the selected symmetric-key encryption. Native tests do not establish that security premise or a native failure probability.

Start with the [result and evidence map](docs/experiment-map.md), [measurement definitions](docs/methodology.md), and [limits](docs/limitations.md). Files under [paper/](paper/) and [submission/](submission/) are **frozen historical editorial artifacts**: they predate the current IND-CPA revision and result presentation. They are retained for provenance; this update does not distribute the current manuscript or submission materials.

## Current evaluation: core rebuild

Start with [experiments/core_rebuild/README.md](experiments/core_rebuild/README.md) for the current implementation, exact reproduction commands and acceptance records. Run `core_20261001_001` contains 28 complete conditions at `N=1024`, ten sessions and 5,880 complete physical tasks. It compares packed retrieval with matched-layout and independently configured concurrent repeated retrieval, using shared preprocessing and a common four-CPU guest affinity pool. The [full-precision summary](experiments/core_rebuild/results/core_20261001_001/summary.json), [all session effects](experiments/core_rebuild/results/core_20261001_001/session_effects.csv) and [configuration/buffer data](experiments/core_rebuild/results/core_20261001_001/configurations_and_buffers.csv) preserve the complete matrix, including weaker results. Historical measurements are kept separate.

The portable `analyze` route recomputes the frozen session estimator in an explicitly new output root; `redraw` reads the verified summary without bootstrapping or native execution. The core README records the actual isolated checks and dependency identities. Current manuscript/PDF/submission materials are excluded from this update; remote publication acceptance is a separate step.

## Historical quick start: redraw earlier results

Native code and archive extraction are unnecessary for this route. Use Python with the pinned analysis dependencies in a virtual environment of your choice:

```bash
git clone https://github.com/sea0114/single-query-packed-multi-record-xpir-for-JISA.git
cd single-query-packed-multi-record-xpir-for-JISA
python3 -m pip install -r requirements-analysis.txt
python3 -B scripts/verify_release.py
python3 -B scripts/present_results.py --root . --out results_redraw_01
```

Choose an unused output directory. The presentation command reads included canonical summaries and CSV; it does not resample, run native code, combine experiments, or change estimators. It creates the earlier 32-condition primary figure, 24-condition retrieval-count figure, complete 96-condition primary figure, supporting tables, full-precision display data, and an input/output hash manifest. All plot caches remain in the output directory. The [experiment map](docs/experiment-map.md) lists inputs and outputs; historical `paper/generated/` is not the comparison target for that earlier presentation revision.

That earlier presentation was checked against unchanged canonical summaries, separately from historical exact statistical replay and native functional validation. Matplotlib 3.10.9 and mpmath 1.3.0 are pinned in `requirements-analysis.txt`; historical exact replay used Python 3.12.3. Other interpreter/rendering environments may produce different PDF bytes without changing coordinates.

## Historical archive: inspect or replay earlier observations

The existing [versioned data archive](data/research-data-20260926.tar.gz) is 28,726,108 bytes, SHA256 `056cbacbf6c622d42c76aae8951ac9003792c4c4c07699dec3560e9c89373a05`. It restores 230,566,247 bytes of exact data/reference evidence. [data-archives.json](manifests/data-archives.json) records every member. Extraction validates paths and bytes before writing and refuses different existing files:

```bash
python3 -B scripts/unpack_data.py
python3 -B scripts/verify_release.py --data
```

Use the separate [historical replay instructions](docs/data-layout.md#historical-statistical-replay) only when statistical recomputation is wanted. That route includes the original bootstrap calculation and is not part of the shortest redraw route or this update's verification. Raw observations, schedules/seeds, failed-attempt rules and scientific hash pins remain unchanged. A checksum verifies integrity, not scientific validity.

## Historical native build and functional validation

[building.md](docs/building.md) documents pinned upstream acquisition, Linux dependencies, build writes, API limits and functional-only commands. Source is distributed without old native executables or system libraries. The upstream fetcher verifies all 142 original file hashes. Building writes shared derived sources and a current-build selector, so use an independent checkout. Rebuilt binaries have new identities and do not inherit historical benchmark pins.

The earlier release validation used Ubuntu 24.04.1 under WSL2, GNU C++ 13.3.0 and one arithmetic thread per retrieval process. It passed 208 functional tasks / 448 fresh-key processes, six rejection checks, 81 source/analysis/runner tests and 26 encoding/correctness tests. These are **historical results**, documented in [validation.md](docs/validation.md); none was rerun for this presentation update. Functional validation collects no performance observations.

New measurements are separate. They require an idle host checked for competing workloads, explicit CPU/memory policies, new build/configuration/run identities, a frozen schedule and failure/stopping rules, and independent raw/results directories. Do not disable old pins, overwrite observations, pool new samples with these experiments, or choose sample counts from observed effects. The earlier presentation update collected no new measurements; the separately identified core rebuild above does.

## Citation, availability and licenses

Use the authors and software title in [CITATION.cff](CITATION.cff), and record the exact checkout with `git rev-parse HEAD`. A fixed URL has the form `https://github.com/sea0114/single-query-packed-multi-record-xpir-for-JISA/tree/<actual-commit>`; substitute the commit used. The earlier [validated research package](https://github.com/sea0114/single-query-packed-multi-record-xpir-for-JISA/tree/bc13e9b67a5f9a8229664362be280cf81fbe43a8) remains a historical version, not a claim that it contains this update. Repository history, visibility and archived evidence are preserved.

Project-owned programs listed in [LICENSE_SCOPE.csv](LICENSE_SCOPE.csv) use **GPL-3.0-or-later**, with the GPLv3 text in [LICENSE](LICENSE). Third-party terms and original notices remain intact; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Text, figures, documentation and data are **not automatically covered by the code license**, and no separate blanket license is granted here. Rights-uncertain upstream files are obtained separately from the official source and are not redistributed as project-owned code.

Report reproducibility problems through Issues with the commit, platform, command, output path and error summary. Do not attach credentials, secret keys or confidential datasets.
